EMC-Zabbix-Integration
=======================

This template and supporting scripts have been developed to integrate EMC VNX storage into the Open-Source Monitoring Tool Zabbix (http://www.zabbix.com)

## Description
This project aims to provide a simple to implement integration for the collection of performance and health data from EMC VNX and CLARiiON based systems into the Zabbix Open-Source monitoring framework. 

This integration is expected to flex many of Zabbix's features including Low Level Discovery, application based separation, and visualization.


## Installation

*Prerequisites*

1.  EMC ECOM Server installed with Storage arrays registered (make sure it's been running for a few hours to build out the object model and collect some stats)
2.  Python module: pywbem, argparse(If Python < 2.7)


A script in the tools subdir can be used to easily add the array to the ECOM server if you are unfamiliar with the ECOM tools

*Installation*

1.  Place the two python scripts included here in the external scripts directory for your zabbix server, be sure they are owned by, and executable by the zabbix user.
2.  Edit the emc_vnx_stats.py script, confirming that the path to the zabbix_sender command is correct along with the path to the agentd configuration file.
2.  Confirm that the script Timeout value is set to 30 seconds in the zabbix_server.conf file.
4.  Create a new host in Zabbix, with a hostname of the ARRAY SERIAL, the visible hostname may be whatever you like.
5.  Create a host macro {$ECOMIP} with a value of the IP address of the ECOM server.
6.  Create host macros: {$ECOMUSER}, {$ECOMPASS} with the ECOM username and password.
5.  Update the Host inventory, setting it to manual to include the array serial number
6.  Import the template and link to the newly added host
7.  Patiently wait for the discovery and first sync to run


## Currently Supported Objects
* Harware Monitoring
  * Storage Processors
  * Enclosures
  * Fans
  * Batteries (SPS)
  * Disks
  * LCC Cards
* Storage Processors
  * Discovery
  * Up/Down validation
  * Performance Metrics
    * SP % Utilization
    * IO % Read
    * IO % Write
    * Cache Flush (Idle, High, Low Watermark)
    * Cache % Dirty
    * Queue Length & Arrivals
* Physical Disks
  * Discovery
  * Performance Metrics
    * Physical Disk Utilization
    * IO % Read
    * Total Read/Write IOs
    * KB Read/Written/Transferred
    * Queue Length & Arrivals
* Volumes
  * Discovery
  * Performance Metrics
    * Volume Utilization
    * Total Read/Write IOs
    * KB Read/Written/Transferred
    * Queue Length & Arrivals
    * Prefetched KB
    * FAST Cache Hits & Misses
    * Disk Crossings
    * Forced Flushes
* Pools & RAID Groups
  * Discovery
  * Capacity/Subscribed
  * Performance Metrics

## Future

* Volumes
  * Capacity/Subscribed
  * Tresspassed or not
  * Response Time
* Pools
  * RG Type
  * Volume Offset

Licensing
---------
Licensed under the Apache License, Version 2.0 (the License); you may not use this file except in compliance with the License. You may obtain a copy of the License at <http://www.apache.org/licenses/LICENSE-2.0>

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

Support
-------
Please file bugs and issues at the Github issues page.
