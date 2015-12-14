EMC-Zabbix-Integration
=======================

This template and supporting scripts have been developed to integrate EMC VNX storage into the Open-Source Monitoring Tool Zabbix (http://www.zabbix.com)


Installation
------------

1.  Install the EMC ECOM Server and register the storage array(s) you wish to monitor
2.  Install the pyWBEM modules onto the Zabbix Server
3.  Place the two python scripts included here in the external scripts directory for your zabbix server, be sure they are executable by the zabbix user.
4.  Update the headers of the scripts to include the IP address of your ECOM server and any other environment specific parameters
5.  Create a new host in Zabbix, with a hostname of the ARRAY SERIAL, the visible hostname may be whatever you like
6.  Update the Host inventory to include the array serial number
7.  Import the template and link to the newly added host


