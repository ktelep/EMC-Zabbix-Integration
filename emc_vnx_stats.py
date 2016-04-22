#!/bin/env python

import os
import csv
import sys
import argparse
import pywbem
import StringIO
import subprocess
import logging
import logging.handlers
from collections import defaultdict
from datetime import datetime, timedelta

log_level = logging.INFO

# User Configurable Parameters
# --------------------------------
sender_command = "/usr/local/bin/zabbix_sender"
config_path = "/etc/zabbix_agentd.conf"
sample_interval = 5    # in minutes, must be >= 5

# Globals
# --------------------------------
stat_manifest_info = dict()
stat_manifest_info["SP"] = {"InstanceID": "FEAdapt", "ManifestID": 2}
stat_manifest_info["Volumes"] = {"InstanceID": "Volume", "ManifestID": 5}
stat_manifest_info["Disks"] = {"InstanceID": "Disk", "ManifestID": 1}

# These align with the proper entries in Clar_Blockmanifest
# 0 = Array
# 1 = Disks
# 2 = SPs
# 3 = SP Ports
# 4 = Snap
# 5 = Volumes


def convert_to_local(timestamp):
    """ Convert the CIM timestamp to a local one,
        correcting for an invalid TZ setting and DST """

    # Convert timestamp to datetime object, stripping UTC offset
    time_stamp = datetime.strptime(timestamp[:-4], "%Y%m%d%H%M%S.%f")
    zone_offset = int(timestamp[-4:])

    # Calculte the time in UTC based on the array's assumed offset
    utc_time = time_stamp - timedelta(minutes=zone_offset)

    # Recalculate time based on current timezone
    offset = datetime.now() - datetime.utcnow()
    local_time = utc_time + offset

    return local_time


def total_seconds(timedelta):
    """ Hack for python 2.6, provides total seconds in a timedelta object """
    return (
        timedelta.microseconds + 0.0 +
        (timedelta.seconds + timedelta.days * 24 * 3600) * 10 ** 6) / 10 ** 6


def get_array_instancename(ecom_conn, array_serial):
    """ Returns the InstanceName of the array serial provided """

    registered_arrays = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    for array in registered_arrays:
        if array_serial in array['Name']:
            return array

    # No array found
    return None


def ecom_connect(ecom_ip, ecom_user, ecom_pass, default_namespace="/root/emc"):
    """ returns a connection to the ecom server """
    ecom_url = "https://%s:5989" % ecom_ip

    return pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                 default_namespace="/root/emc")


def get_sample_interval(ecom_conn, array_serial):
    """ Returns the current sample interval in minutes """

    array = get_array_instancename(ecom_conn, array_serial)

    SampleInterval = ecom_conn.Associators(
        array, ResultClass="CIM_StatisticsCollection",
        PropertyList=["SampleInterval"])

    interval = total_seconds(SampleInterval[0]["SampleInterval"].timedelta)

    return interval/60


def set_sample_interval(ecom_conn, array_serial, sample_interval):

    array = get_array_instancename(ecom_conn, array_serial)

    SampleInterval = ecom_conn.Associators(
        array, ResultClass="CIM_StatisticsCollection",
        PropertyList=["SampleInterval"])

    new_interval = timedelta(minutes=sample_interval)

    SampleInterval[0]["SampleInterval"] = pywbem.CIMDateTime(new_interval)

    ecom_conn.ModifyInstance(SampleInterval[0],
                             PropertyList=["SampleInterval"])

    return


def get_stats(array_serial, ecom_ip, instance_id, ecom_user="admin",
              ecom_pass="#1Password"):
    """ Collect performance statistics """

    ecom_conn = ecom_connect(ecom_ip, ecom_user, ecom_pass)

    # Check and set the sample interval
    interval = get_sample_interval(ecom_conn, array_serial)
    if interval != sample_interval:
        set_sample_interval(ecom_conn, array_serial, sample_interval)

    # Determine the sequence our Stats are coming in from the Manifest
    array = get_array_instancename(ecom_conn, array_serial)
    man_coll = ecom_conn.AssociatorNames(
        array, ResultClass="CIM_BlockStatisticsManifestCollection")[0]

    manifests = ecom_conn.Associators(
        man_coll, ResultClass="CIM_BlockStatisticsManifest")

    for i in manifests:
        if instance_id in i["InstanceID"]:
            header_row = i["CSVSequence"]

    # Grab our stats
    stats_service = ecom_conn.AssociatorNames(
        array, ResultClass="CIM_BlockStatisticsService")[0]

    stat_output = ecom_conn.InvokeMethod("GetStatisticsCollection",
                                         stats_service,
                                         StatisticsFormat=pywbem.Uint16(2))

    return (header_row, stat_output[1]["Statistics"])


def process_stats(header_row, stat_output, array_serial, manifest_info,
                  ignore_fields=[]):
    """ Pushes statistics out to Zabbix """

    sp_data = stat_output[stat_manifest_info[manifest_info]["ManifestID"]]
    f = StringIO.StringIO(sp_data)
    reader = csv.reader(f, delimiter=';')

    timestamp_index = header_row.index("StatisticTime")
    perf_dev_id_index = header_row.index("InstanceID")

    ignore_fields = ignore_fields + ["ElementType",
                                     "StatisticTime",
                                     "InstanceID"]

    skip_fields = []

    for i in ignore_fields:
        skip_fields.append(header_row.index(i))

    zabbix_data = []

    timestamp = None
    for row in reader:

        if not timestamp:
            timestamp = convert_to_local(row[timestamp_index]).strftime("%s")

        perf_dev_id = row[perf_dev_id_index]

        for i in range(0, len(header_row)):
            if i in skip_fields:
                continue
            elif row[i] == "18446744073709551615":   # If the data is N/A
                continue
            zabbix_key = "emc.vnx.perf.%s[%s]" % (header_row[i], perf_dev_id)
            zabbix_data.append("%s %s %s %s" % (array_serial, zabbix_key,
                                                timestamp, row[i]))
            
    print "------------------------------------------------------"
    current_time = datetime.now().strftime("%c")
    stat_time = datetime.fromtimestamp(int(timestamp)).strftime("%c")
    print "Current Time: %s    Stat Time: %s" % (current_time, stat_time)

    # Check if we've already collected and sent this dataset
    last_stat = None

    last_file = "/tmp/%s_last.tmp" % manifest_info
    stat_file = "/tmp/%s_data.tmp" % manifest_info

    if os.path.isfile(last_file):
        with open(last_file) as f:
            last_stat = f.readline()

    if timestamp != last_stat:
        with open(stat_file, "w") as f:
            f.write("\n".join(zabbix_data))

        subprocess.call([sender_command, "-v", "-c", config_path,
                         "-s", array_serial, "-T", "-i", stat_file])

        print "\n".join(zabbix_data)
        print "\n"

        with open(last_file, "w") as f:
            f.write(timestamp)

    else:
        print "Already posted stats to Zabbix, skipping"

    print "------------------------------------------------------\n"


def sp_stats_query(array_serial, ecom_ip, ecom_user="admin",
                   ecom_pass="#1Password"):

    InstanceID = stat_manifest_info["SP"]["InstanceID"]

    header_row, stat_output = get_stats(array_serial, ecom_ip, InstanceID,
                                        ecom_user, ecom_pass)

    process_stats(header_row, stat_output, array_serial, "SP")


def volume_stats_query(array_serial, ecom_ip, ecom_user="admin",
                       ecom_pass="#1Password"):

    InstanceID = stat_manifest_info["Volumes"]["InstanceID"]

    header_row, stat_output = get_stats(array_serial, ecom_ip, InstanceID,
                                        ecom_user, ecom_pass)

    skip_fields = ["EMCRaid3Writes", "EMCSnapCacheReads",
                   "EMCSnapCacheWrites", "EMCSnapLogicalUnitReads",
                   "EMCSnapTLUReads", "EMCSnapTLUWrites",
                   "EMCSnapLargeWrites", "EMCSPAIOTimeCounter",
                   "EMCSPBIOTimeCounter", "EMCSPAIdleTimeCounter",
                   "EMCSPBIdleTimeCounter", "EMCSPAReadIOs",
                   "EMCSPBReadIOs", "EMCSPAWriteIOs",
                   "EMCSPBWriteIOs", "EMCKBytesSPARead",
                   "EMCKBytesSPBRead", "EMCKBytesSPAWritten",
                   "EMCKBytesSPBWritten", "EMCNonZeroQueueArrivals",
                   "EMCQueueLengthsOnArrival", "EMCNonZeroRequestArrivals",
                   "EMCSPANonZeroRequestArrivals",
                   "EMCSPBNonZeroRequestArrivals",
                   "EMCOutstandingRequests", "EMCSPAOutstandingRequests",
                   "EMCSPBOutstandingRequests", "EMCImplicitTresspasses",
                   "EMCSPAImplicitTresspasses", "EMCSPBImplicitTresspasses",
                   "EMCExplicitTresspasses", "EMCSPAExplicitTresspasses",
                   "EMCSPBExplicitTresspasses", "EMCLoggingTime",
                   "EMCReadHistogram", "EMCReadHistogramOverflows",
                   "EMCWriteHistogram", "EMCWriteHistogramOverflows"]

    process_stats(header_row, stat_output, array_serial, "Volumes",
                  skip_fields)

    # Calculate our response times

def disk_stats_query(array_serial, ecom_ip, ecom_user="admin",
                     ecom_pass="#1Password"):

    InstanceID = stat_manifest_info["Disks"]["InstanceID"]

    header_row, stat_output = get_stats(array_serial, ecom_ip, InstanceID,
                                        ecom_user, ecom_pass)

    skip_fields = ["EMCSpinUPS", "EMCCurrentPWRSavingLogTimeStamp",
                   "EMCSpinningCounter", "EMCStandbyCounter"]

    process_stats(header_row, stat_output, array_serial, "Disks", skip_fields)


def pool_stats_query(array_serial, ecom_ip, ecom_user="admin",
                     ecom_pass="#1Password"):

    ecom_conn = ecom_connect(ecom_ip, ecom_user, ecom_pass)

    # Lets locate our array
    array_list = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    array = None

    for i in array_list:
        if i["Name"] == "CLARiiON+%s" % array_serial:
            array = i

    # Walk our pools for stats
    pool_classes = ["EMC_UnifiedStoragePool", "EMC_DeviceStoragePool",
                    "EMC_VirtualProvisioningPool"]

    processed_stats = ["TotalManagedSpace", "RemainingManagedSpace",
                       "EMCPercentSubscribed", "EMCSubscribedCapacity",
                       "EMCEFDCacheEnabled"]

    zabbix_data = []
    timestamp = datetime.now().strftime("%s")

    for pool_class in pool_classes:
        for i in ecom_conn.Associators(array, ResultClass=pool_class):
            for stat in processed_stats:
                try:
                    zabbix_key = "emc.vnx.perf.%s[%s]" % (
                        stat, i["InstanceID"].replace(" ", "_"))
                    zabbix_data.append("%s %s %s %s" % (array_serial,
                                                        zabbix_key,
                                                        timestamp,
                                                        i[stat]))
                except KeyError:
                    pass

    stat_file = "/tmp/pool_data.tmp"

    with open(stat_file, "w") as f:
        f.write("\n".join(zabbix_data))

    subprocess.call([sender_command, "-v", "-c", config_path,
                    "-s", array_serial, "-T", "-i", stat_file])

    print "\n".join(zabbix_data)
    print "\n"


def hardware_healthcheck(array_serial, ecom_ip, ecom_user="admin",
                         ecom_pass="#1Password"):

    ecom_conn = ecom_connect(ecom_ip, ecom_user, ecom_pass)

    # Generate our timestamp
    timestamp = datetime.now().strftime("%s")
    zabbix_data = []

    # Lets locate our array
    array_list = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    array = None

    for i in array_list:
        if i["Name"] == "CLARiiON+%s" % array_serial:
            array = i

    # Devices we're just locating status on
    health_classes = ["EMC_LinkControlDevice", "EMC_PowerDevice",
                      "EMC_BatteryDevice", "EMC_StorageProcessorSystem",
                      "EMC_DiskDrive"]

    for device in health_classes:
        dev_instance = ecom_conn.Associators(array, ResultClass=device)
        for inst in dev_instance:
            status = " ".join(inst["StatusDescriptions"])
            if "DiskDrive" in device:
                device_id = inst["SystemName"] + "+" + inst["Name"]
            elif "StorageProcessor" in device:
                device_id = inst["EMCBSPInstanceID"]
            else:
                device_id = inst["DeviceID"]

            zabbix_key = "emc.vnx.health.Status[%s]" % device_id
            zabbix_data.append("%s %s %s %s" % (array_serial, zabbix_key,
                                                timestamp, status))

    # For enclosures we need to locate the ArrayChassis
    chassis_list = ecom_conn.EnumerateInstanceNames("EMC_ArrayChassis")
    array_chassis = None

    for i in chassis_list:
        if array_serial in i["Tag"]:
            array_chassis = i

    # Now we can locate enclosures
    enclosures = ecom_conn.Associators(array_chassis,
                                       ResultClass="EMC_EnclosureChassis")

    for inst in enclosures:
        status = " ".join(inst["StatusDescriptions"])
        device_id = inst["Tag"]
        zabbix_key = "emc.vnx.health.Status[%s]" % device_id
        zabbix_data.append("%s %s %s %s" % (array_serial, zabbix_key,
                                            timestamp, status))

    stat_file = "/tmp/health_data.tmp"

    with open(stat_file, "w") as f:
        f.write("\n".join(zabbix_data))

    subprocess.call([sender_command, "-v", "-c", config_path,
                    "-s", array_serial, "-T", "-i", stat_file])

    print "\n".join(zabbix_data)
    print "\n"


def get_pool_io_stats(ecom_conn, array, disk_id_list, vol_id_list):
    # We are using these as a cache for block stats
    cim_stats = None
    disk_sequence = None
    vol_sequence = None

    # Determine the order that the stats are provided, this is the CSVSequence
    # from the block manifest

    if not disk_sequence:
        manifest = ecom_conn.EnumerateInstanceNames("Clar_BlockManifest")

        for i in manifest:
            if "Disk" in i["InstanceID"]:
                inst = ecom_conn.GetInstance(i)
                disk_sequence = inst["CSVSequence"]
            if "Volume" in i["InstanceID"]:
                inst = ecom_conn.GetInstance(i)
                vol_sequence = inst["CSVSequence"]

    if not cim_stats:
        # Grab our block stats service for the array
        block_stats = ecom_conn.AssociatorNames(
            array, ResultClass="Clar_BlockStatisticsService")[0]

        # Pull statistics, Elementtypes 8 and 10 (Volumes and Disks)
        cim_stats = ecom_conn.InvokeMethod(
            "GetStatisticsCollection", block_stats,
            StatisticsFormat=pywbem.Uint16(2),
            ElementTypes=[pywbem.Uint16(8), pywbem.Uint16(10)])

    disk_stat = StringIO.StringIO(cim_stats[1]["Statistics"][0])  # Disk stats
    vol_stat = StringIO.StringIO(cim_stats[1]["Statistics"][1])  # Vol Stats

    # The parameters we care about
    pool_stats = ["TotalIOs", "KBytesTransferred", "ReadIOs", "KBytesRead",
                  "WriteIOs", "KBytesWritten"]

    disk_index_info = {}
    vol_index_info = {}
    totals_disk = {}
    totals_vol = {}

    timestamp = None

    for i in pool_stats:
        disk_index_info[disk_sequence.index(i)] = i
        vol_index_info[vol_sequence.index(i)] = i
        totals_disk[disk_sequence.index(i)] = 0
        totals_vol[vol_sequence.index(i)] = 0

    # Disk Stats
    reader = csv.reader(disk_stat, delimiter=';')
    for row in reader:
        if row[0] in disk_id_list:
            for j in disk_index_info.keys():
                totals_disk[j] = totals_disk[j] + int(row[j])
            timestamp = row[2]

    # Volume Stats
    reader = csv.reader(vol_stat, delimiter=';')
    for row in reader:
        if row[0] in vol_id_list:
            for j in vol_index_info:
                totals_vol[j] = totals_vol[j] + int(row[j])
            timestamp = row[2]

    # Build the resultset
    results = defaultdict(dict)
    for i in disk_index_info.keys():
        results["disks"][disk_index_info[i]] = totals_disk[i]
    for i in vol_index_info.keys():
        results["volumes"][vol_index_info[i]] = totals_vol[i]
    results["timestamp"] = convert_to_local(timestamp).strftime("%s")

    return results


def pool_performance(req_pool, array_serial, ecom_ip,
                     ecom_user="admin", ecom_pass="#1Password"):

    array_pool = req_pool.replace("_", " ")

    ecom_conn = ecom_connect(ecom_ip, ecom_user, ecom_pass)

    # Lets locate our array
    array_list = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    array = None

    for i in array_list:
        if i["Name"] == "CLARiiON+%s" % array_serial:
            array = i

    pools = ecom_conn.AssociatorNames(array, ResultClass="EMC_StoragePool")

    zabbix_data = []
    for pool in pools:
        if array_pool in pool["InstanceID"]:

            pool_disks = ecom_conn.Associators(
                pool, AssocClass="CIM_ConcreteDependency",
                ResultClass="CIM_DiskDrive")

            pool_volumes = ecom_conn.Associators(
                pool, ResultClass="CIM_StorageVolume")

            disk_list = []
            for i in pool_disks:
                perf_dev_id = "CLAR+%s+Disk+%s" % (array_serial, i["Name"])
                disk_list.append(perf_dev_id)

            vol_list = []
            for i in pool_volumes:
                vol_list.append(i["EMCBSPInstanceID"])

            stats = get_pool_io_stats(ecom_conn, array, disk_list, vol_list)

            timestamp = stats["timestamp"]
            for i in stats["disks"].keys():
                zabbix_key = "emc.vnx.perf.PoolDisk%s[%s]" % (i, req_pool)
                zabbix_data.append("%s %s %s %s" % (array_serial, zabbix_key,
                                                    timestamp,
                                                    str(stats["disks"][i])))

            for i in stats["volumes"].keys():
                zabbix_key = "emc.vnx.perf.PoolVol%s[%s]" % (i, req_pool)
                zabbix_data.append("%s %s %s %s" % (array_serial, zabbix_key,
                                                    timestamp,
                                                    str(stats["volumes"][i])))

    print "------------------------------------------------------"
    current_time = datetime.now().strftime("%c")
    stat_time = datetime.fromtimestamp(int(timestamp)).strftime("%c")
    print "Current Time: %s    Stat Time: %s" % (current_time, stat_time)

    # Check if we've already collected and sent this dataset
    last_stat = None

    last_file = "/tmp/poolperf_%s_last.tmp" % req_pool
    stat_file = "/tmp/poolperf_%s_data.tmp" % req_pool

    if os.path.isfile(last_file):
        with open(last_file) as f:
            last_stat = f.readline()

    if timestamp != last_stat:
        with open(stat_file, "w") as f:
            f.write("\n".join(zabbix_data))

        subprocess.call([sender_command, "-v", "-c", config_path,
                         "-s", array_serial, "-T", "-i", stat_file])

        print "\n".join(zabbix_data)
        print "\n"

        with open(last_file, "w") as f:
            f.write(timestamp)

    else:
        print "Already posted stats to Zabbix, skipping"

    print "------------------------------------------------------\n"

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
   
    log_file = '/tmp/emc_vnx_stats.log'
    setup_logging(log_file)

    logger = logging.getLogger('discovery')

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
                       help="Collect Stats on Physical Disks")
    group.add_argument('--volumes', '-v', action="store_true",
                       help="Collect Stats on Volumes/LUNs")
    group.add_argument('--procs', '-p', action="store_true",
                       help="Collect Stats on Storage Processors")
    group.add_argument('--pools', '-o', action="store_true",
                       help="Collect Stats on Physical Disks")
    group.add_argument('--array', '-a', action="store_true",
                       help="Collect Stats on Array devices and enclosures")
    group.add_argument('--poolperf', '-r', action="store",
                       help="Collect individual perf stats on a pool")

    args = parser.parse_args()
    logger.debug("Arguments parsed: %s" % str(args))

    # Check for zabbix_sender and agentd files
    if not os.path.isfile(sender_command):
        logging.info("Unable to find sender command at: %s" % sender_command)
        print ""
        print "Unable to locate zabbix_sender command at: %s" % sender_command
        print "Please update the script with the appropriate path"
        sys.exit()

    if not os.path.isfile(config_path):
        logging.info("Unable to find zabbix_agentd.conf at: %s" % config_path)
        print ""
        print "Unable to locate zabbix_agentd.conf file at: %s" % config_path
        print "Please update the script with the appropriate path"
        sys.exit()

    if args.disks:
        disk_stats_query(args.serial, args.ecom_ip,
                         args.ecom_user, args.ecom_pass)
        sys.exit()
    elif args.volumes:
        volume_stats_query(args.serial, args.ecom_ip,
                           args.ecom_user, args.ecom_pass)
        sys.exit()
    elif args.procs:
        sp_stats_query(args.serial, args.ecom_ip,
                       args.ecom_user, args.ecom_pass)
        sys.exit()
    elif args.pools:
        pool_stats_query(args.serial, args.ecom_ip,
                         args.ecom_user, args.ecom_pass)
        sys.exit()
    elif args.array:
        hardware_healthcheck(args.serial, args.ecom_ip,
                             args.ecom_user, args.ecom_pass)
    elif args.poolperf:
        pool_performance(args.poolperf, args.serial, args.ecom_ip,
                         args.ecom_user, args.ecom_pass)
        sys.exit()


if __name__ == "__main__":
    main()
