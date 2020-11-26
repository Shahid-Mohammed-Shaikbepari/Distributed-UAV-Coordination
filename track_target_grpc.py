#!/usr/bin/python

# Set target (waypoint) positions for UAVs

import sys
import struct
import socket
import math
import time
import argparse
import glob
import subprocess
import threading
import datetime
#import pdb

from core.api.grpc import client
from core.api.grpc import core_pb2
import xmlrpc.client


uavs = []
# live list of all nodes: 0 -- dead; 1 - alive
ack_list = {1:0, 2:0, 3:0, 4:0, 6:0, 7:0, 8:0, 9:0 }
intention_list = {}
# trackedList maintains which target is maintained by whom
trackedList = {}
expirationTimer = 2
mynodeseq = 0
nodecnt = 0
protocol = 'none'
mcastaddr = '235.1.1.1'
port = 9100
ttl = 64
core = None
session_id = None 

filepath = '/tmp'
nodepath = ''

thrdlock = threading.Lock()
xmlproxy = xmlrpc.client.ServerProxy("http://localhost:8000", allow_none=True)


#---------------
# Define a CORE node
#---------------
class CORENode():
  def __init__(self, nodeid, track_nodeid):
    self.nodeid = nodeid
    self.trackid = track_nodeid
    self.oldtrackid = track_nodeid
    self.last_seen = None
    self.cur_intention = -1

  def __repr__(self):
    return str(self.nodeid)
    
    
#---------------
# Thread that receives UDP Advertisements
#---------------
class ReceiveUDPThread(threading.Thread):    
  def __init__(self):
    threading.Thread.__init__(self)
    
  def run(self):
    ReceiveUDP()

# reseting ack list to 0's for all nodes
def AckList_reset():
  global ack_list
  ack_list = {1:0, 2:0, 3:0, 4:0, 6:0, 7:0, 8:0, 9:0}

#---------------
# Calculate the distance between two modes (on a map)
#---------------
def Distance(node1, node2):
  return math.sqrt(math.pow(node2.y-node1.y, 2) + math.pow(node2.x-node1.x, 2))

#---------------
# Redeploy a UAV back to its original position
#---------------
def RedeployUAV(uavnode):
  print("Redeploy UAV")
  position = xmlproxy.getOriginalWypt()
  xmlproxy.setWypt(position[0], position[1])

#---------------
# Record target tracked to the proxy 
# Update UAV color depending if it is tracking a target
#---------------
def RecordTarget(uavnode):
  print("RecordTarget")
  xmlproxy.setTarget(uavnode.trackid)


#---------------
# Advertise the target being tracked over UDP
#---------------
def AdvertiseUDP(buf):
  print("AdvertiseUDP")
  addrinfo = socket.getaddrinfo(mcastaddr, None)[0]
  sk = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
  ttl_bin = struct.pack('@i', ttl)
  sk.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_bin)
  #buf = str(intention_flag) + ' ' + str(uavnodeid) + ' ' + str(trgtnodeid)
  sk.sendto(buf.encode(encoding='utf-8',errors='strict'), (addrinfo[4][0], port))
  print("timestamp", datetime.datetime.now())
  #print("I'm advertising this", buf)

#---------------
# Receive and parse UDP advertisments
#---------------
def ReceiveUDP():
  #print("Receive UDP")
  addrinfo = socket.getaddrinfo(mcastaddr, None)[0]
  sk = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
  sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  # Bind
  sk.bind(('', port))

  # Join group
  group_bin = socket.inet_pton(addrinfo[0], addrinfo[4][0])
  mreq = group_bin + struct.pack('=I', socket.INADDR_ANY)
  sk.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

  while 1:
    print("ReceiveUDP")
    buf, sender = sk.recvfrom(1500)
    buf_str = buf.decode('utf-8')
    myuavnode = uavs[mynodeseq]
    packet = buf_str.split(" ")
    #print("ReceiveUDP", packet)
    if packet[0] == "ack":
      updateAck_list(packet, myuavnode)
      
    elif packet[0] == "in":
      sendAckPacket(packet, myuavnode)
      #trgtidstr, intention_str, uavidstr  = buf_str.split(" ")        
      #intention_flag, uavnodeid, trgtnodeid =  int(packet[1]), int(packet[2])
      #print("timestamp", datetime.datetime.now())
      #print("intention_flag, uavnodeid, trgtnodeid", intention_str, uavidstr, trgtidstr)
      # its a contention packet I need to sent an ack back
      #if intention_flag:	
      #intention_list[uavnodeid] = trgtnodeid
    #its a normal status pack
    else:
      uavnodeid, trgtnodeid = int(packet[0]), int(packet[1])
      UpdateTracking(uavnodeid, trgtnodeid)
    #trgtidstr, intention_str, uavidstr  = buf_str.split(" ")        
    #intention_flag, uavnodeid, trgtnodeid = int(intention_str), int(uavidstr), int(trgtidstr)
    #print("timestamp", datetime.datetime.now())
    #print("intention_flag, uavnodeid, trgtnodeid", intention_str, uavidstr, trgtidstr)
    # its a contention packet I need to sent an ack back
    #if intention_flag:	
    #  intention_list[uavnodeid] = trgtnodeid
      
    # Update tracking info for other UAVs
    #myuavnode = uavs[mynodeseq]
    #if myuavnode.nodeid != uavnodeid:
    #  UpdateTracking(uavnodeid, trgtnodeid)

def updateAck_list(packet, myuavnode):
  senderUAV = int(packet[1])
  receiverUAV = int(packet[2])
  trgtnodeid = int(packet[3])
  if receiverUAV == myuavnode.nodeid and trgtnodeid == myuavnode.cur_intention:
    ack_list[senderUAV] = 1
    #print("got ack from ", senderUAV, "for targetnode: ", trgtnodeid, "updated it to ack list")
    print("intention list: ", intention_list)
    print("ack list: ", ack_list)
    print('tarcking list', trackedList)

#make an acket pack
def createAckPacket(senderUAVid, receiverUAVid, targetid):
  buf = 'ack' + ' ' + str(senderUAVid) + ' ' + str(receiverUAVid) + ' ' + str(targetid)
  return buf
  
def sendAckPacket(packet, myuavnode):
  #print("sendAckPacket")
  # its a contention packet I need to sent an ack back
  #trgtidstr, intention_str, uavidstr  = buf_str.split(" ") 
  uavnodeid, trgtnodeid =  int(packet[1]), int(packet[2])
  buf = createAckPacket(myuavnode.nodeid, uavnodeid, trgtnodeid)
  AdvertiseUDP(buf)
  #todo: send it
  #print("timestamp", datetime.datetime.now())
  #print("intention_flag, uavnodeid, trgtnodeid", intention_str, uavidstr, trgtidstr)
  intention_list[uavnodeid] = trgtnodeid
    
#---------------
# Update tracking info based on a received advertisement
#---------------
def UpdateTracking(uavnodeid, trgtnodeid):
  print("UpdateTracking")
  if protocol == "udp":
    thrdlock.acquire()
    
  # Update corresponding UAV node structure with tracking info
  # if UAV node is in the UAV list
  in_uavs = False
  for uavnode in uavs:
    if uavnode.nodeid == uavnodeid:
      uavnode.trackid = trgtnodeid
      uavnode.last_seen = time.time()
      in_uavs = True

  # Otherwise add UAV node to UAV list
  if not in_uavs:
    node = CORENode(uavnodeid, trgtnodeid)
    node.last_seen = time.time()
    uavs.append(node)   
    
    #print("node details", node.nodeid, node.last_seen)
  #update in tracking list that this node is tracking this particular target with current time stamp
  trackedList[trgtnodeid] = (uavnodeid, time.time())    
  if protocol == "udp":
    thrdlock.release()

def CreateIntentionPacket(uavnodeid, trgtnodeid):
  return 'in' + ' ' + str(uavnodeid) + ' ' + str(trgtnodeid)
  
#to consult with other nodes and make a decision
def Mutual_Consultation(uavnode, trgtnodeid):
  print("Mutual_Consultation")
	#create a intention message and send it, just make one more entry into the same function as intention flag
  #intention_list.clear();	
  # I'm sending a intention message I want to make sure all the live nodes got it
  # by getting back their acks
  # reset the acklist for this particular target
  #print("ack_list before reset: ", ack_list)
  AckList_reset()
  #ack_list = {1:0, 2:0, 3:0, 4:0, 6:0, 7:0, 8:0, 9:0}
  #print("ack_list after reset: ", ack_list)
  #AdvertiseUDP(1, uavnode.nodeid, trgtnodeid)
  #AdvertiseUDP(1, uavnode.nodeid, uavnode.trackid)
  #AdvertiseUDP(1, uavnode.nodeid, uavnode.trackid)
  #AdvertiseUDP(1, uavnode.nodeid, uavnode.trackid)
#go for sleep for 1/2 of second till everyone sends their opinion
  #print("timestamp", datetime.datetime.now())
  #print("Going for sleep now")
  #thrdlock.release()
  #time.sleep(2)
  #print("timestamp", datetime.datetime.now())
  #print("Just wokeup from sleep now")
  #thrdlock.acquire()
  # I should get data from all the live nodes, else retransmit
  AllgotPacket = False
  while not AllgotPacket:
    for uavnodetmp in uavs:
    #make decision if he is alive
      #print("uavnodetmp.nodeid", uavnodetmp.nodeid, "uavnodetmp.last_seen", uavnodetmp.last_seen)
      if uavnodetmp.last_seen - time.time() <= 1:
      #so he is alive, check if you have got an ack from him
      #you did not get a ack from him, retransmit
        if ack_list[uavnodetmp.nodeid] == 0:
          uavnode.cur_intention = trgtnodeid
          buf = CreateIntentionPacket(uavnode.nodeid, trgtnodeid)
          AdvertiseUDP(buf)
  #AdvertiseUDP(1, uavnode.nodeid, uavnode.trackid)
  #AdvertiseUDP(1, uavnode.nodeid, uavnode.trackid)
  #AdvertiseUDP(1, uavnode.nodeid, uavnode.trackid)
  #go for sleep for 1/2 of second till everyone sends their opinion
          #print("timestamp", datetime.datetime.now())
          print("Going for sleep now")  
          thrdlock.release()
          time.sleep(1)
          #print("timestamp", datetime.datetime.now())
          print("Just wokeup from sleep now")
          thrdlock.acquire()
          break
    else:
      print("received all acks")
      AllgotPacket = True
  #todo: I also need to make sure that I received everyone's constent   
  track_flag = 1
  for node_id, target_id in intention_list.items():
    print("in for loop")
    # make sure by the time you went to sleep no one else started targeting it
    #if someone is already tracking or any node lesser than my node id has intention to track it, I drop
    if trgtnodeid in trackedList or (target_id == trgtnodeid and uavnode.nodeid > node_id):			
      track_flag = 0	
      #todo: tracking list could have been updated here		
      break
	
#by protocol our node is eligible for tracking the target
  return track_flag
	

#---------------
# Update waypoints for targets tracked, or track new targets
#---------------
def TrackTargets(covered_zone, track_range):
  #print("Track Targets")
  uavnode = uavs[mynodeseq]
  uavnode.trackid = -1
  updatewypt = 0

  commsflag = 0
  if protocol == "udp":
    commsflag = 1

  potential_targets = xmlproxy.getPotentialTargets(covered_zone, track_range)

  print("UAV nodes: ", uavs)
  print("Potential Targets: ", potential_targets)

  for trgtnode_id in potential_targets:
    #trackflag is for that particular target id
    trackflag = 0
    print('tarcking list', trackedList)
    if trgtnode_id in trackedList:
      #get current system time and get the last update time, verify it is less than expiration timer, 
      #otherwise remove entry
      curTime = time.time()
      lastEntry = trackedList.get(trgtnode_id)[1]
      if curTime - lastEntry < expirationTimer:
        print(trgtnode_id," Already being tracked by someone, no need to track it")
        trackflag = 1
      if curTime - lastEntry >= expirationTimer:  
        print(f'remove target {trgtnode_id} and node entry {trackedList.get(trgtnode_id)[0]} from tagets tracklist maybe target went out of range')
        trackedList.pop(trgtnode_id)
        
    # If this UAV was tracking this target before and it's still
    # in range then it should keep it.
    # Update waypoint to the new position of the target
    if uavnode.oldtrackid == trgtnode_id:
         # Keep the current tracking; no need to change
        # unless the track goes out of range
        print('Keep the current tracking; no need to change ', trgtnode_id)
        uavnode.trackid = trgtnode_id
        updatewypt = 1     

    # If this UAV was not tracking any target and finds one in range
    # and no one else is tracking it
    if not trackflag and uavnode.oldtrackid == -1:
      print("Node %d found potential target %d" % (uavnode.nodeid, trgtnode_id))
      #if commsflag == 1:
        #todo: can comment below part
        #for uavnodetmp in uavs:
         # if uavnodetmp.trackid == trgtnode_id or \
         #     (uavnodetmp.trackid == 0 and uavnodetmp.oldtrackid == trgtnode_id):
          #  print("Target ", trgtnode_id, " is being tracked already")
          #  trackflag = 1
            
      if commsflag == 0 or trackflag == 0: 
        # UAV node should track this target
	#i want to track this but first lets check with everyone
	# write a function and do the decision making, and return back here
        if Mutual_Consultation(uavnode, trgtnode_id):
          print("UAV node should track this target ", trgtnode_id)
          uavnode.trackid = trgtnode_id
          #no need to update in trackedList, becuase current itself is tracking it
          #lets update it to trackedList so that I dont look someone else to track again
          #now lets break from this loop and update color and send notification to others
          trackedList[trgtnode_id] = (uavnode.nodeid, time.time())
          updatewypt = 1
          break

    if updatewypt == 1:
      # Update waypoint for UAV node
      print("Update waypoint")
      updatewypt = 0
      response = core.get_node(session_id, trgtnode_id)
      node = response.node
      trgtnode_x, trgtnode_y = node.position.x, node.position.y
      xmlproxy.setWypt(int(trgtnode_x), int(trgtnode_y))

  # Reset tracking info for other UAVs if we're using comms
  if commsflag == 1:
    for uavnodetmp in uavs:
      if uavnodetmp.nodeid != uavnode.nodeid:
        uavnodetmp.oldtrackid = uavnodetmp.trackid
        uavnodetmp.trackid = 0
          
  # Advertise target being tracked if using comms 
  if protocol == "udp":
    #send a status packet
    buf = CreateStatusPacket(uavnode.nodeid, uavnode.trackid)   
    AdvertiseUDP(buf)
    #AdvertiseUDP(0, uavnode.nodeid, uavnode.trackid)
    #AdvertiseUDP(0, uavnode.nodeid, uavnode.trackid)
    #AdvertiseUDP(0, uavnode.nodeid, uavnode.trackid) 	
    
  #this code will only hit if there is a change in node's tracking  
  # Record the target tracked for displaying proper colors
  # Re-deploy UAV if it's not track anything
  if uavnode.trackid != uavnode.oldtrackid:
    uavnode.oldtrackid = uavnode.trackid
    RecordTarget(uavnode)
    if uavnode.trackid == -1:
      RedeployUAV(uavnode)

def CreateStatusPacket(uavnodeid, trackid):
  return str(uavnodeid) + ' ' + str(trackid)
  
#---------------
# main
#---------------
def main():
  global uavs
  global protocol
  global nodepath
  global mynodeseq
  global nodecnt
  global core
  global session_id
  #global ack_list

  # Get command line inputs 
  parser = argparse.ArgumentParser()
  parser.add_argument('-my','--my-id', dest = 'uav_id', metavar='my id',
                      type=int, default = '1', help='My Node ID')
  parser.add_argument('-c','--covered-zone', dest = 'covered_zone', metavar='covered zone',
                       type=int, default = '1200', help='UAV covered zone limit on X axis')
  parser.add_argument('-r','--track_range', dest = 'track_range', metavar='track range',
                       type=int, default = '600', help='UAV tracking range')
  parser.add_argument('-i','--update_interval', dest = 'interval', metavar='update interval',
                      type=int, default = '1', help='Update Inteval')
  parser.add_argument('-p','--protocol', dest = 'protocol', metavar='comms protocol',
                      type=str, default = 'none', help='Comms Protocol')

  
  # Parse command line options
  args = parser.parse_args()

  protocol = args.protocol

  # Create grpc client
  core = client.CoreGrpcClient("172.16.0.254:50051")
  core.connect()
  response = core.get_sessions()
  if not response.sessions:
    raise ValueError("no current core sessions")
  session_summary = response.sessions[0]
  session_id = int(session_summary.id)
  session = core.get_session(session_id).session

  # Populate the uavs list with current UAV node information
  mynodeseq = 0
  node = CORENode(args.uav_id, -1)
  uavs.append(node)
  RedeployUAV(node)
  RecordTarget(node)
  nodecnt += 1
  
  if mynodeseq == -1:
    print("Error: my id needs to be in the list of UAV IDs")
    sys.exit()
    
  # Initialize values
  corepath = "/tmp/pycore.*/"
  nodepath = glob.glob(corepath)[0]
  msecinterval = float(args.interval)
  secinterval = msecinterval/1000
  
  #import pdb; pdb.set_trace()
  #import pdb
  #breakpoint()

  #pdb.set_trace()
  
  if protocol == "udp":
    # Create UDP receiving thread
    recvthrd = ReceiveUDPThread()
    recvthrd.start()
        
  # Start tracking targets
  while 1:
    time.sleep(secinterval)

    if protocol == "udp":    
      thrdlock.acquire()
    
    TrackTargets(args.covered_zone, args.track_range)

    if protocol == "udp":
      thrdlock.release()


if __name__ == '__main__':
  main()
