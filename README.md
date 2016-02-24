EMC-Zabbix-Integration
=======================

This template and supporting scripts have been developed to integrate EMC VNX storage into the Open-Source Monitoring Tool Zabbix (http://www.zabbix.com)

## Description
This project aims to provide a simple to implement integration for the collection of performance and health data from EMC VNX and CLARiiON based systems into the Zabbix Open-Source monitoring framework. 

This integration is expected to flex many of Zabbix's features including Low Level Discovery, application based separation, and visualization.


## Installation

*Prerequisites*

1.  Confirm that block statistics collection is enabled on your array:  https://community.emc.com/docs/DOC-24564
1.  EMC ECOM Server is installed with Storage arrays registered (make sure it's been running for a few hours to build out the object model and collect some stats)
    * Be sure you read the Installation documentation for the ECOM to confirm you have all of the necessary 32 and 64 bit libraries installed for your OS.
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

*Troubleshooting*

* Discovery Issues
    *  Check the /tmp/emc_vnx_discovery.log file for any exceptions.
    *  Check that you can run the scripts from the command line AS THE ZABBIX USER successfully, if you can run them from the command line but not from within Zabbix, you may want to confirm the host macros and host name have been properly configured.

* Stats Collection Issues 
    *  Each group of statisics have a "Statistics Collection" key that runs the external emc_vnx_stats.py collection script, check the output for exceptions or problems
    *  If you see the error "ERROR_FAMILY_OPERATION_NOT_AVAILABLE Statistics Service is not enabled for array"  Be sure that you have Block Statistics data collection enabled (See https://community.emc.com/docs/DOC-24564)


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
    * Response Time
* Pools & RAID Groups
  * Discovery
  * Capacity/Subscribed
  * Performance Metrics

## Future

* Volumes
  * Capacity/Subscribed
  * Tresspassed or not
* Pools
  * RG Type
  * Volume Offset

Licensing
---------
This software is provided under the MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
Status API Training Shop Blog About Pricing


Support
-------
Please file bugs and issues at the Github issues page.
