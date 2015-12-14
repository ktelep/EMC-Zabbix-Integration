#!/bin/env python

import sys
import json
import getopt
import pywbem


ecom_ip = "10.5.36.148"

ecom_queries = dict()
ecom_queries["physical_disk"]= "SELECT * FROM CIM_DiskDrive where SystemName='CLARiiON+%s'"
ecom_queries["volume"]="SELECT * FROM CIM_StorageVolume where SystemName='CLARiiON+%s'"
ecom_queries["storage_proc"]="SELECT * FROM CIM_RemoteServiceAccessPoint where SystemName LIKE 'CLARiiON+%s'"

def discover_array_volumes(array_serial, ecom_ip, ecom_user="admin",
                        ecom_pass="#1Password"):
    """Discover the Volumes in the VNX array


       Arguments-
           array_serial:  (string) Serial number of array to discover
           ecom_ip:       (string) IP Address of SMI-S/ECOM Server
           ecom_user:     (string) Username for ECOM auth, default is "admin"
           ecom_pass:     (string) Password for ECOM auth, default is "$1Password"

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """
    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url,(ecom_user,ecom_pass),
                                      default_namespace="/root/emc")

    volumes = ecom_conn.ExecQuery("DMTF:CQL",
                                         ecom_queries["volume"] % array_serial)

    discovered_volumes = []
    for volume in volumes:

        diskitem = dict()
        diskitem["{#VOLDEVICEID}"] = volume["DeviceID"]
        diskitem["{#VOLALIAS}"] = volume["ElementName"]
        diskitem["{#VOLPERFDEVICEID}"] = volume["EMCBSPInstanceID"]
        diskitem["{#ARRAYSERIAL}"] = array_serial

        discovered_volumes.append(diskitem)

    return discovered_volumes


def discover_array_disks(array_serial, ecom_ip, ecom_user="admin",
                        ecom_pass="#1Password"):
    """Discover the disks in the VNX array


       Arguments-
           array_serial:  (string) Serial number of array to discover
           ecom_ip:       (string) IP Address of SMI-S/ECOM Server
           ecom_user:     (string) Username for ECOM auth, default is "admin"
           ecom_pass:     (string) Password for ECOM auth, default is "$1Password"

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """
    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url,(ecom_user,ecom_pass),
                                      default_namespace="/root/emc")

    physical_disks = ecom_conn.ExecQuery("DMTF:CQL",
                                         ecom_queries["physical_disk"] % array_serial)

    discovered_disks = []
    for disk in physical_disks:
        
        dev_id = disk["DeviceID"]
        perf_dev_id = dev_id.replace("CLARiiON+","CLAR+%s+Disk+" % array_serial)
        bus_enc = dev_id.replace("CLARiiON+","").split('_')
	dev_name = "Bus %s Enclosure %s Slot %s" % (bus_enc[0], bus_enc[1], bus_enc[2])
         
        diskitem = dict()
        diskitem["{#DISKDEVICEID}"] = dev_id
        diskitem["{#DISKPERFDEVICEID}"] = perf_dev_id
        diskitem["{#ARRAYSERIAL}"] = array_serial
        diskitem["{#DISKNAME}"] = dev_name
  
        discovered_disks.append(diskitem)


    return discovered_disks

def discover_array_SPs(array_serial, ecom_ip, ecom_user="admin",
                        ecom_pass="#1Password"):
    """Discover the SPs in the VNX array


       Arguments-
           array_serial:  (string) Serial number of array to discover
           ecom_ip:       (string) IP Address of SMI-S/ECOM Server
           ecom_user:     (string) Username for ECOM auth, default is "admin"
           ecom_pass:     (string) Password for ECOM auth, default is "$1Password"

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """
    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url,(ecom_user,ecom_pass),
                                      default_namespace="/root/emc")

    storage_procs = ecom_conn.ExecQuery("DMTF:CQL",
                                        ecom_queries["storage_proc"] % array_serial)

    discovered_procs = []
    for proc in storage_procs:
        dev_id = proc['SystemName']
        sp_name = dev_id[-4:].replace("_","")
        perf_dev_id = "CLAR+%s+FEAdapt+SP-%s" % (array_serial,sp_name[-1])
        sp_ip = proc['AccessInfo']
        
        spitem = dict()
        spitem["{#SPDEVICEID}"] = dev_id
        spitem["{#SPPERFDEVICEID}"] = perf_dev_id
        spitem["{#SPNAME}"] = sp_name
        spitem["{#SPIP}"] = sp_ip
       
        discovered_procs.append(spitem)

    return discovered_procs 

def zabbix_safe_output(data):
  
    return json.dumps({"data": data})

def main():

    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:dvph",
                                   ["serial=",'disks','volumes','procs','help'])
    except getopt.GetoptError as err:
        print(err)
        sys.exit(2)
    
    array_serial = None
    item = None
    
    for o, a in opts:
        if o in ("-s","--serial"):
            array_serial = a
        elif o in ("-d","--disks"):
            item = "Disks"
        elif o in ("-d","--volumes"):
            item = "Volumes"
        elif o in ("-p","--procs"):
            item = "SPs"

    if not array_serial:
        print "No serial provided"
        sys.exit(2)
    elif not item:
        print "No item specified for discover"
        sys.exit(2)

    if item == "Disks":
        print zabbix_safe_output(discover_array_disks(array_serial, ecom_ip))
        sys.exit()
    elif item == "Volumes":
        print zabbix_safe_output(discover_array_volumes(array_serial, ecom_ip))
        sys.exit()
    elif item == "SPs":
        print zabbix_safe_output(discover_array_SPs(array_serial, ecom_ip))
        sys.exit()


if __name__ == "__main__":
    main()

   

