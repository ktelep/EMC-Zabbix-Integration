#!/bin/env python

import sys
import json
import pywbem
import argparse

# User Configurable Parameters
# --------------------------------
ecom_ip = "10.5.36.50"
ecom_user = "admin"
ecom_pass = "#1Password"

# Global Queries
# --------------------------------
ecom_queries = dict()
ecom_queries["storage_proc"] = "SELECT * FROM CIM_RemoteServiceAccessPoint where SystemName LIKE 'CLARiiON+%s'"

def get_array_instancename(array_serial, ecom_conn):
    """ Returns the InstanceName of the array serial provided """

    registered_arrays = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    for array in registered_arrays:
        if array_serial in array['Name']:
            return array

    # No array found
    return None

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
    ecom_conn = pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                      default_namespace="/root/emc")

    array = get_array_instancename(array_serial,ecom_conn)

    # Locate all volumes associated with the array
    volumes = ecom_conn.Associators(array,ResultClass="CIM_StorageVolume")

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
    ecom_conn = pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                      default_namespace="/root/emc")

    array = get_array_instancename(array_serial, ecom_conn)

    physical_disks = ecom_conn.Associators(array,ResultClass="CIM_DiskDrive")

    discovered_disks = []
    for disk in physical_disks:

        dev_id = disk["DeviceID"]
        perf_dev_id = dev_id.replace(
            "CLARiiON+", "CLAR+%s+Disk+" % array_serial)
        bus_enc = dev_id.replace("CLARiiON+", "").split('_')
        dev_name = "Bus %s Enclosure %s Slot %s" % (
            bus_enc[0], bus_enc[1], bus_enc[2])

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
    ecom_conn = pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                      default_namespace="/root/emc")

    array = get_array_instancename(array_serial, ecom_conn)
    sps = ecom_conn.AssociatorNames(array,ResultClass="EMC_StorageProcessorSystem")
  
    storage_procs = []
    for sp in sps:
        i = ecom_conn.Associators(sp,ResultClass="CIM_RemoteServiceAccessPoint")
        storage_procs.append(i[0])

    discovered_procs = []
    for proc in storage_procs:
        dev_id = proc['SystemName']
        sp_name = dev_id[-4:].replace("_", "")
        perf_dev_id = "CLAR+%s+FEAdapt+SP-%s" % (array_serial, sp_name[-1])
        sp_ip = proc['AccessInfo']

        spitem = dict()
        spitem["{#SPDEVICEID}"] = dev_id
        spitem["{#SPPERFDEVICEID}"] = perf_dev_id
        spitem["{#SPNAME}"] = sp_name
        spitem["{#SPIP}"] = sp_ip

        discovered_procs.append(spitem)

    return discovered_procs

def discover_array_pools(array_serial, ecom_ip, ecom_user="admin",
                       ecom_pass="#1Password"):
    """Discover the Pools in the VNX array


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

    # Lets locate our array
    array = get_array_instancename(array_serial,ecom_conn)

    pool_classes = ["EMC_DeviceStoragePool","EMC_UnifiedStoragePool",
                    "EMC_VirtualProvisioningPool"]

    discovered_pools = []
    for c in pool_classes:
         for pool in ecom_conn.Associators(array,ResultClass=c):
             pool_name = None
             pool_item = dict()
             pool_type = pool["EMCPoolID"][0]
             if pool_type == "C":   # RAID Group
                 pool_name = "RAID Group %s" % pool["PoolID"]
             else:
                 pool_name = pool["PoolID"]
 
             pool_item["{#POOLNAME}"] = pool_name
             pool_item["{#POOLDEVICEID}"] = pool["InstanceID"].replace(" ","_")
             pool_item["{#ARRAYSERIAL}"] = array_serial
 
             discovered_pools.append(pool_item)

    return discovered_pools




def zabbix_safe_output(data):
    """ Generate JSON output for zabbix from a passed in list of dicts """
    return json.dumps({"data": data})


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument('--serial','-s', action="store",
                        help="Array Serial Number", required=True)
    parser.add_argument('--ecom_ip', '-i', action="store",
                        help="IP Address of ECOM server", required=True)

    parser.add_argument('--ecom_user', action="store", 
                        help="ECOM Username", default="admin")
    parser.add_argument('--ecom_pass', action="store", 
                        help="ECOM Password", default="#1Password")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--disks', '-d', action="store_true", 
                        help="Discover Physical Disks")
    group.add_argument('--volumes', '-v', action="store_true", 
                        help="Discover Volumes/LUNs")
    group.add_argument('--procs', '-p', action="store_true", 
                        help="Discover Storage Processors")
    group.add_argument('--pools', '-o', action="store_true", 
                        help="Discover Physical Disks")
    group.add_argument('--array', '-a', action="store_true", 
                        help="Discover Array devices and enclosures")


    args = parser.parse_args()

    result = None
    if args.disks:
        result = discover_array_disks(args.serial, args.ecom_ip, 
                                      args.ecom_user, args.ecom_pass)
    elif args.volumes:
        result = discover_array_volumes(args.serial, args.ecom_ip, 
                                        args.ecom_user, args.ecom_pass)
    elif args.procs: 
        result = discover_array_SPs(args.serial, args.ecom_ip, 
                                    args.ecom_user, args.ecom_pass)
    elif args.pools:
        result = discover_array_pools(args.serial, args.ecom_ip, 
                                      args.ecom_user, args.ecom_pass)
    elif args.array:
         pass

    
    print zabbix_safe_output(result)

if __name__ == "__main__":
    main()
