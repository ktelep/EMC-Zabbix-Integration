#!/bin/env python

import sys
import json
import pywbem
import argparse
import logging
import logging.handlers

log_level = logging.INFO


def ecom_connect(ecom_ip, ecom_user, ecom_pass, default_namespace="/root/emc"):
    """ returns a connection to the ecom server """
    ecom_url = "https://%s:5989" % ecom_ip

    logger = logging.getLogger('discovery')
    logger.info("Building WBEM Connection to %s" % ecom_url)

    return pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                 default_namespace="/root/emc")


def get_array_instancename(array_serial, ecom_conn):
    """ Returns the InstanceName of the array serial provided """

    logger = logging.getLogger('discovery')
    logger.debug("Collecting Array InstanceName for %s" % array_serial)

    registered_arrays = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    for array in registered_arrays:
        if array_serial in array['Name']:
            logger.debug("Array InstanceName located for %s" % array_serial)
            return array

    # No array found
    logging.warning("Array InstanceName for %s not found" % array_serial)
    return None


def discover_array_volumes(ecom_conn, array_serial):
    """Discover the Volumes in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection

       Returns-
           Zabbix compatible List of Hashes to be JSONified
           or appended to additional data

    """

    array = get_array_instancename(array_serial, ecom_conn)

    # Locate all volumes associated with the array
    logger = logging.getLogger('discovery')
    logger.debug("Started volume info collection from ECOM")
    volumes = ecom_conn.Associators(array, ResultClass="CIM_StorageVolume")
    logger.debug("Completed volume info collection ECOM")

    logger.debug("Generating discovery objects")
    discovered_volumes = []
    for volume in volumes:

        diskitem = dict()
        diskitem["{#VOLDEVICEID}"] = volume["DeviceID"]
        diskitem["{#VOLALIAS}"] = volume["ElementName"]
        diskitem["{#VOLPERFDEVICEID}"] = volume["EMCBSPInstanceID"]
        diskitem["{#ARRAYSERIAL}"] = array_serial

        discovered_volumes.append(diskitem)
        logger.debug(str(diskitem))

    return discovered_volumes


def discover_array_disks(ecom_conn, array_serial):
    """Discover the disks in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection

       Returns-
           Zabbix compatible List of Hashes to be JSONified or appended
           to additional data

    """

    array = get_array_instancename(array_serial, ecom_conn)

    logger = logging.getLogger('discovery')
    logger.debug("Started disk info collection from ECOM")
    physical_disks = ecom_conn.Associators(array, ResultClass="CIM_DiskDrive")
    logger.debug("Completed disk info collection from ECOM")

    logger.debug("Generating discovery objects")
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
        logger.debug(str(diskitem))

    return discovered_disks


def discover_array_SPs(ecom_conn, array_serial):
    """Discover the SPs in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection

       Returns-
           Zabbix compatible List of Hashes to be JSONified
           or appended to additional data

    """
    array = get_array_instancename(array_serial, ecom_conn)

    logger = logging.getLogger('discovery')
    logger.debug("Gathering list of SPs from ECOM")
    sps = ecom_conn.AssociatorNames(array,
                                    ResultClass="EMC_StorageProcessorSystem")
    logger.debug("Completed SP list")

    logger.debug("Locating Access Points for SPs from ECOM")

    storage_procs = []
    for sp in sps:
        i = ecom_conn.Associators(sp,
                                  ResultClass="CIM_RemoteServiceAccessPoint")
        storage_procs.append(i[0])

    logger.debug("Completed Locating Access Points for SPs from ECOM")

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
        logger.debug(str(spitem))

    return discovered_procs


def discover_array_pools(ecom_conn, array_serial):
    """Discover the Pools in the VNX array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection

       Returns-
           Zabbix compatible List of Hashes to be JSONified
           or appended to additional data

    """

    # Lets locate our array
    array = get_array_instancename(array_serial, ecom_conn)

    pool_classes = ["EMC_DeviceStoragePool", "EMC_UnifiedStoragePool",
                    "EMC_VirtualProvisioningPool"]

    logger = logging.getLogger('discovery')

    discovered_pools = []
    for c in pool_classes:
        logger.debug("Starting discovery of pools of class: %s" % c)
        for pool in ecom_conn.Associators(array, ResultClass=c):
            pool_name = None
            pool_item = dict()
            pool_type = pool["EMCPoolID"][0]
            if pool_type == "C":   # RAID Group
                pool_name = "RAID Group %s" % pool["PoolID"]
            else:
                pool_name = pool["PoolID"]

            pool_item["{#POOLNAME}"] = pool_name
            pool_item["{#POOLDEVICEID}"] = pool["InstanceID"].replace(" ", "_")
            pool_item["{#ARRAYSERIAL}"] = array_serial

            discovered_pools.append(pool_item)
            logger.debug(str(pool_item))

    return discovered_pools


def discover_array_devices(ecom_conn, array_serial):
    """Discover the enclosures, batteries, etc. in the array

       Arguments-
           ecom_conn:     (pyWBEM) pyWBEM connection

       Returns-
           Zabbix compatible List of Hashes to be JSONified
           or appended to additional data

    """

    array_hardware = []
    # Lets locate our array
    array = get_array_instancename(array_serial, ecom_conn)

    # Enclosures are associated with the ArrayChassis of the Storage System
    logger = logging.getLogger('discovery')
    logger.debug("Collecting Array Chassis info from ECOM")
    array_chassis = ecom_conn.AssociatorNames(
        array, ResultClass="EMC_ArrayChassis")[0]

    logger.debug("Completed Array Chassis")

    enclosures = ecom_conn.Associators(array_chassis,
                                       ResultClass="EMC_EnclosureChassis")

    logger.debug("Completed EnclosureChassis")

    for i in enclosures:
        if "SPE" in i["ElementName"]:
            enclosure_name = "Storage Processor Enclosure"
        else:
            enc_addr = tuple(i["ElementName"].split('_'))
            enclosure_name = "Bus %s Enclosure %s" % enc_addr

        hardware = {"{#ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": i["Tag"],
                    "{#DEVICENAME}": enclosure_name,
                    "{#DEVICETYPE}": "Enclosure"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    # Power Supplies
    logger.debug("Collecting power supplies from ECOM")
    pow_supplies = ecom_conn.Associators(array, ResultClass="EMC_PowerDevice")
    logger.debug("Completed collecting power supplies from ECOM")

    for i in pow_supplies:
        location = i["DeviceID"].split('+')
        device = location[2]
        supply_side = location[-1]

        if 'SPE' in device:
            device = "SPE Power Supply "   # Strip out the N/As
        else:
            enc_addr = tuple(device.split('_'))
            device = "Bus %s Enclosure %s Power Supply " % enc_addr

        device = device + supply_side

        hardware = {"{#ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": i["DeviceID"],
                    "{#DEVICENAME}": device,
                    "{#DEVICETYPE}": "Supply"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    # Batteries
    logger.debug("Collecting batteries from ECOM")
    batteries = ecom_conn.Associators(array, ResultClass="EMC_BatteryDevice")
    logger.debug("Completed collecting batteries from ECOM")

    for i in batteries:
        location = i["DeviceID"].split('+')
        device = location[2]
        battery_side = location[-1]

        if "SPE" in device:
            device = "Storage Processor Enclosure Battery "
        else:
            device = "Bus %s Enclosure %s Battery " % tuple(device.split('_'))

        device = device + battery_side

        hardware = {"{ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": i["DeviceID"],
                    "{#DEVICENAME}": device,
                    "{#DEVICETYPE}": "Battery"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    # LCC Cards
    logger.debug("Collecting LCC cards from ECOM")
    lcc_cards = ecom_conn.Associators(array,
                                      ResultClass="EMC_LinkControlDevice")
    logger.debug("Completed collecting LCC cards from ECOM")

    for i in lcc_cards:
        location = i["DeviceID"].split('+')
        device = location[2]
        side = location[-1]

        device = "Bus %s Enclosure %s LCC Card " % tuple(device.split('_'))

        device = device + side

        hardware = {"{ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": i["DeviceID"],
                    "{#DEVICENAME}": device,
                    "{#DEVICETYPE}": "LCC"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    # Fans (Fun fact, NOT all arrays have monitored fans in them!)
    # If no FAN data is reported, physically check your array...
    logger.debug("Collecting Fans from ECOM")
    fans = ecom_conn.Associators(array, ResultClass="EMC_FanDevice")
    logger.debug("Completed collecting Fans from ECOM")

    for i in fans:
        location = i["DeviceID"].split('+')
        device = location[2]
        side = location[-1]

        device = "Bus %s Enclosure %s Fan " % tuple(device.split('_'))

        device = device + side

        hardware = {"{ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": i["DeviceID"]+"+Fan",
                    "{#DEVICENAME}": device,
                    "{#DEVICETYPE}": "Fan"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    # Storage Processors
    logger.debug("Collecting SP hardware from ECOM")
    sps = ecom_conn.Associators(array,
                                ResultClass="EMC_StorageProcessorSystem")
    logger.debug("Completed collecting SP hardware from ECOM")
    for i in sps:
        device = "Storage Processor %s" % (i["Name"].split('_')[-1])
        hardware = {"{#ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": i["Name"],
                    "{#DEVICENAME}": device,
                    "{#DEVICETYPE}": "SP"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    # Disks
    logger.debug("Collecting Disk hardware from ECOM")
    disks = ecom_conn.Associators(array, ResultClass="CIM_DiskDrive")
    logger.debug("Completed collecting Disk hardware from ECOM")

    for i in disks:
        dev_id = "CLARiiON+%s+%s" % (array_serial, i["Name"])
        bus_enc = i["Name"].split('_')
        dev_name = "Disk at Bus %s Enclosure %s Slot %s" % (
            bus_enc[0], bus_enc[1], bus_enc[2])

        hardware = {"{#ARRAYSERIAL}": array_serial,
                    "{#DEVICEID}": dev_id,
                    "{#DEVICENAME}": dev_name,
                    "{#DEVICETYPE}": "Disk"
                    }

        array_hardware.append(hardware)
        logger.debug(str(hardware))

    return array_hardware


def zabbix_safe_output(data):
    """ Generate JSON output for zabbix from a passed in list of dicts """
    logger = logging.getLogger('discovery')
    logger.info("Generating output")
    output = json.dumps({"data": data}, indent=4, separators=(',', ': '))

    logger.debug(json.dumps({"data": data}))

    return output

def log_exception_handler(type, value, tb):
    logger = logging.getLogger('discovery')
    logger.exception("Uncaught exception: {0}".format(str(value)))

def setup_logging(log_file):
    """ Sets up our file logging with rotation """
    my_logger = logging.getLogger('discovery')
    my_logger.setLevel(log_level)

    handler = logging.handlers.RotatingFileHandler(
                          log_file, maxBytes=5120000, backupCount=5)

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(process)d %(message)s')
    handler.setFormatter(formatter)

    my_logger.addHandler(handler)

    sys.excepthook = log_exception_handler
 
    return


def main():

    log_file = '/tmp/emc_vnx_discovery.log'
    setup_logging(log_file)

    logger = logging.getLogger('discovery')
    logger.debug("Discovery script started")

    parser = argparse.ArgumentParser()

    parser.add_argument('--serial', '-s', action="store",
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

    logger.debug("Arguments parsed: %s" % str(args))

    ecom_conn = ecom_connect(args.ecom_ip, args.ecom_user, args.ecom_pass)

    result = None
    if args.disks:
        logger.info("Disk discovery started")
        result = discover_array_disks(ecom_conn, args.serial)
    elif args.volumes:
        logger.info("Volume discovery started")
        result = discover_array_volumes(ecom_conn, args.serial)
    elif args.procs:
        logger.info("Storage Processor discovery started")
        result = discover_array_SPs(ecom_conn, args.serial)
    elif args.pools:
        logger.info("Pool discovery started")
        result = discover_array_pools(ecom_conn, args.serial)
    elif args.array:
        logger.info("Array hardware discovery started")
        result = discover_array_devices(ecom_conn, args.serial)

    print zabbix_safe_output(result)

    logger.info("Discovery Complete")

if __name__ == "__main__":
    main()
