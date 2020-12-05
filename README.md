# Drone_project
The project is we eight drones and eight targets in a WLAN, we want our drones to track these targets without any conflict.

### Technologies: tracking UAVs code was written in Python, CORE was used for emulation

### Distributed Systems:
All the drones are treated as distributed systems, without having a central controling unit they all have to coordinate and track only one target and no two drones 
should target one single target.

### Agreement Protocol:
When a target comes in range of the drones, all the drones who are not tracking target sense it and want to track it, so that create an intention packet and broadcast 
it, all the nodes(drones) who received the intention packet sends an acknowledgement packet back to the sender of intention packet. All the nodes who has an intention 
track the particular target distributedly generate a random number and send it as well, the drone which generated the largest random number gets it. And rest of the drones
leave it

### Packets Design:
I've designed three kinds of packets for the communications among them viz. Status packet, Intention Packet, and Acknowledgement Packet with different fields

### Results:
Acheived all the drones tracking different targets in with a low latency of avg 10-15 seconds depending upon the delay and packet drop rate

### Images

#### Initially when targets are away from drones
![](images/Screenshot%20from%202020-12-04%2018-40-39.png)

#### As soon as all targets are brought into the range of drones
![](images/Screenshot%20from%202020-12-04%2018-41-38.png)

#### The drones start tracking the target distributedly without two drones tracking same target
![](images/Screenshot%20from%202020-12-04%2018-41-41.png)

#### All the drones tracking different targets
![](images/Screenshot%20from%202020-12-04%2018-42-28.png)

![](images/Screenshot%20from%202020-12-04%2018-42-29.png)
