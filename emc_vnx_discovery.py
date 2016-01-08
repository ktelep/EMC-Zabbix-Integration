#!/bin/env python

import sys
import json
import pywbem
import argparse

# User Configurable Parameters
# --------------------------------
ecom_user = "admin"
ecom_pass = "#1Password"


def ecom_connect(ecom_ip, ecom_user, ecom_pass, default_namespace="/root/emc"):
    """ returns a connection to the ecom server """
    ecom_url = "https://%s:5989" % ecom_ip

    return pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                 default_namespace="/root/emc")

def get_array_instancename(array_serial, ecom_conn):
    """ Returns the InstanceName of the array serial provided """

    registered_arrays = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    for array in registered_arrays:
        if array_serial in array['Name']:
            return array

    # No array found
    return None

def discover_array_volumes(ecom_conn, array_serial):
    """Discover the Volumes in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection 

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """

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


def discover_array_disks(ecom_conn, array_serial):
        
    """Discover the disks in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection 

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """

    array = get_array_instancename(array_serial, ecom_conn)

    physical_disks = ecom_conn.Associators(array,ResultClass="CIM_DiskDrive")

    discovered_disks = []
    for disk in physical_disks:

        dev_id = "CLAR+%s+%s" % (array_serial, disk["Name"])
        perf_dev_id = "CLAR+%s+Disk+%s" % (array_serial, disk["Name"])
        bus_enc = disk["Name"].split('_')
        dev_name = "Bus %s Enclosure %s Slot %s" % (
            bus_enc[0], bus_enc[1], bus_enc[2])

        diskitem = dict()
        diskitem["{#DISKDEVICEID}"] = dev_id
        diskitem["{#DISKPERFDEVICEID}"] = perf_dev_id
        diskitem["{#ARRAYSERIAL}"] = array_serial
        diskitem["{#DISKNAME}"] = dev_name

        discovered_disks.append(diskitem)

    return discovered_disks


def discover_array_SPs(ecom_conn, array_serial):
    """Discover the SPs in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection 

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """
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

def discover_array_pools(ecom_conn, array_serial):

    """Discover the Pools in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection 

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """

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


def discover_array_devices(ecom_conn, array_serial):

    """Discover the enclosures, batteries, etc. in the array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection 

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended to additional data

    """

    array_hardware = []
    # Lets locate our array
    array = get_array_instancename(array_serial,ecom_conn)

    # Enclosures are associated with the ArrayChassis of the Storage System
    array_chassis = ecom_conn.AssociatorNames(array,
                                              ResultClass="EMC_ArrayChassis")[0]
    enclosures = ecom_conn.Associators(array_chassis,
                                  ResultClass="EMC_EnclosureChassis")

    for i in enclosures:
        if "SPE" in i["ElementName"]:
            enclosure_name = "Storage Processor Enclosure"
        else:
            enclosure_name = "Bus %s Enclosure %s" % tuple(i["ElementName"].split('_'))

        array_hardware.append({"{#ARRAYSERIAL}": array_serial,
                               "{#DEVICEID}": i["Tag"],
                               "{#DEVICENAME}": enclosure_name,
                               "{#DEVICETYPE}": "Enclosure"
                              })

    # Power Supplies
    pow_supplies = ecom_conn.Associators(array,ResultClass="EMC_PowerDevice")
    
    for i in pow_supplies:
        location = i["DeviceID"].split('+')
        device = location[2]
        supply_side = location[-1]

        if 'SPE' in device:
           device = "SPE Power Supply "   # Strip out the N/As
        else:
           device = "Bus %s Enclosure %s Power Supply " % tuple(device.split('_'))

        device = device + supply_side

        array_hardware.append({"{#ARRAYSERIAL}":array_serial,
                               "{#DEVICEID}": i["DeviceID"],
                               "{#DEVICENAME}": device,
                               "{#DEVICETYPE}": "Supply"
                              })

    # Batteries
    batteries = ecom_conn.Associators(array,ResultClass="EMC_BatteryDevice")

    for i in batteries: 
        location = i["DeviceID"].split('+')
        device = location[2]
        battery_side = location[-1]

        if "SPE" in device:
           device = "Storage Processor Enclosure Battery "
        else:
           device = "Bus %s Enclosure %s Battery " % tuple(device.split('_'))
 
        device = device + battery_side

        array_hardware.append({"{ARRAYSERIAL}":array_serial,
                               "{#DEVICEID}": i["DeviceID"],
                               "{#DEVICENAME}": device,
                               "{#DEVICETYPE}": "Battery"
                              })

    # LCC Cards
    lcc_cards = ecom_conn.Associators(array,ResultClass = "EMC_LinkControlDevice")

    for i in lcc_cards:
        location = i["DeviceID"].split('+')
        device = location[2]
        side = location[-1]

        device = "Bus %s Enclosure %s LCC Card " % tuple(device.split('_'))

        device = device + side
     
        array_hardware.append({"{ARRAYSERIAL}":array_serial,
                               "{#DEVICEID}": i["DeviceID"],
                               "{#DEVICENAME}": device,
                               "{#DEVICETYPE}": "LCC"
                              })
    
    # Fans (Fun fact, NOT all arrays have monitored fans in them!) 
    # If no FAN data is reported, physically check your array...
    fans = ecom_conn.Associators(array,ResultClass="EMC_FanDevice") 
    for i in fans:
        location = i["DeviceID"].split('+')
        device = location[2]
        side = location[-1]

        device = "Bus %s Enclosure %s Fan " % tuple(device.split('_'))

        device = device + side
     
        array_hardware.append({"{ARRAYSERIAL}":array_serial,
                               "{#DEVICEID}": i["DeviceID"]+"+Fan",
                               "{#DEVICENAME}": device,
                               "{#DEVICETYPE}": "Fan"
                              })
    

    # Storage Processors
    sps = ecom_conn.Associators(array,ResultClass="EMC_StorageProcessorSystem")
    for i in sps:
        device = "Storage Processor %s" % (i["Name"].split('_')[-1])
        array_hardware.append({"{#ARRAYSERIAL}":array_serial,
                               "{#DEVICEID}": i["Name"],
                               "{#DEVICENAME}": device,
                               "{#DEVICETYPE}": "SP"
                              })

    # Disks
    disks = ecom_conn.Associators(array,ResultClass="CIM_DiskDrive")
    for i in disks:

        dev_id = "CLARiiON+%s+%s" % (array_serial, i["Name"])
        bus_enc = i["Name"].split('_')
        dev_name = "Disk at Bus %s Enclosure %s Slot %s" % (
            bus_enc[0], bus_enc[1], bus_enc[2])

        array_hardware.append({"{#ARRAYSERIAL}": array_serial,
                               "{#DEVICEID}": dev_id,
                               "{#DEVICENAME}": dev_name,
                               "{#DEVICETYPE}": "Disk"
                              })
 
    return array_hardware

                               

def zabbix_safe_output(data):
    """ Generate JSON output for zabbix from a passed in list of dicts """
    return json.dumps({"data": data}, indent=4, separators=(',', ': '))


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

    ecom_conn = ecom_connect(args.ecom_ip, args.ecom_user, args.ecom_pass)

    result = None
    if args.disks:
        result = discover_array_disks(ecom_conn, args.serial)
    elif args.volumes:
        result = discover_array_volumes(ecom_conn, args.serial)
    elif args.procs: 
        result = discover_array_SPs(ecom_conn, args.serial)
    elif args.pools:
        result = discover_array_pools(ecom_conn, args.serial)
    elif args.array:
        result = discover_array_devices(ecom_conn, args.serial)

    
    print zabbix_safe_output(result)

if __name__ == "__main__":
    main()
