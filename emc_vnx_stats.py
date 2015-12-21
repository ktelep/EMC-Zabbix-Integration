#!/bin/env python

import os
import csv
import sys
import argparse
import pywbem
import datetime
import StringIO
import subprocess
from datetime import datetime, timedelta

# User Configurable Parameters
# --------------------------------
ecom_ip = "10.5.36.50"
sender_command = "/usr/local/bin/zabbix_sender"
config_path = "/etc/zabbix_agentd.conf"
sample_interval = 5    # in minutes, must be >= 5

# Globals
# --------------------------------
stat_manifest_info = dict()
stat_manifest_info["SP"] = {"InstanceID": "CLARiiON+%s"
                                          "+EMC_MANIFEST_DEFAULT+FEAdapt",
                            "ManifestID": 2}
stat_manifest_info["Volumes"] = {"InstanceID": "CLARiiON+%s"
                                               "+EMC_MANIFEST_DEFAULT+Volume",
                                 "ManifestID": 5}
stat_manifest_info["Disks"] = {"InstanceID": "CLARiiON+%s"
                                             "+EMC_MANIFEST_DEFAULT+Disk",
                               "ManifestID": 1}

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


def get_stats(array_serial, ecom_ip, instance_id, ecom_user="admin",
              ecom_pass="#1Password"):
    """ Collect performance statistics """

    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url, (ecom_user, ecom_pass),
                                      default_namespace="/root/emc")

    q = "SELECT SampleInterval from CIM_StatisticsCollection where " \
        "InstanceID='CLARiiON+%s'"

    info = ecom_conn.ExecQuery("DMTF:CQL", q % array_serial)

    # Determine if the interval if 5 minutes, if not reset it to 10 minutes
    if sample_interval < 10:
        cim_dt = "00000000000%s00.000000:000" % (str(sample_interval))
    else:
        cim_dt = "0000000000%s00.000000:000" % (str(sample_interval))

    if info[0]["SampleInterval"] != pywbem.CIMDateTime(cim_dt):
        print "Setting interval to %d minutes" % (sample_interval)
        info[0]["SampleInterval"] = pywbem.CIMDateTime(cim_dt)
        ecom_conn.ModifyInstance(info[0], PropertyList=["SampleInterval"])

    # Figure out what stats we're gathering

    q = "SELECT * FROM Clar_Blockmanifest where InstanceID='%s'"
    manifest = ecom_conn.ExecQuery("DMTF:CQL", q % instance_id)

    header_row = manifest[0]["CSVSequence"]

    stats_service = pywbem.CIMInstanceName("Clar_BlockStatisticsService",
                                           keybindings=pywbem.NocaseDict({
                                               'CreationClassName': 'Clar_BlockStatisticsService',
                                               'SystemName':  'CLARiiON+' + array_serial,
                                               'Name': 'EMCBlockStatisticsService',
                                               'SystemCreationClassName': 'Clar_StorageSystem'
                                           }), namespace='/root/emc')

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
    element_type_index = header_row.index("ElementType")

    skip_fields = [timestamp_index, perf_dev_id_index, element_type_index]

    for i in ignore_fields:
        skip_fields.append(header_row.index(i))

    zabbix_data = []

    timestamp = None
    for row in reader:

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
    print "Current Time: %s    Stat Time: %s" % (datetime.now().strftime("%c"),
                                                 datetime.fromtimestamp(int(timestamp)).strftime("%c"))

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

    InstanceID = stat_manifest_info["SP"]["InstanceID"] % array_serial

    header_row, stat_output = get_stats(array_serial, ecom_ip, InstanceID,
                                        ecom_user, ecom_pass)

    process_stats(header_row, stat_output, array_serial, "SP")


def volume_stats_query(array_serial, ecom_ip, ecom_user="admin",
                       ecom_pass="#1Password"):

    InstanceID = stat_manifest_info["Volumes"]["InstanceID"] % array_serial

    header_row, stat_output = get_stats(array_serial, ecom_ip, InstanceID,
                                        ecom_user, ecom_pass)

    skip_fields = ["EMCRaid3Writes", "EMCSampledReadsTime", 
                   "EMCSampledWritesTime", "EMCSnapCacheReads",
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
                   "EMCSPANonZeroRequestArrivals", "EMCSPBNonZeroRequestArrivals",
                   "EMCOutstandingRequests", "EMCSPAOutstandingRequests",
                   "EMCSPBOutstandingRequests", "EMCImplicitTresspasses",
                   "EMCSPAImplicitTresspasses", "EMCSPBImplicitTresspasses",
                   "EMCExplicitTresspasses", "EMCSPAExplicitTresspasses",
                   "EMCSPBExplicitTresspasses", "EMCLoggingTime",
                   "EMCReadHistogram", "EMCReadHistogramOverflows",
                   "EMCWriteHistogram", "EMCWriteHistogramOverflows"]

    process_stats(header_row, stat_output, array_serial, "Volumes", skip_fields)


def disk_stats_query(array_serial, ecom_ip, ecom_user="admin",
                     ecom_pass="#1Password"):

    InstanceID = stat_manifest_info["Disks"]["InstanceID"] % array_serial

    header_row, stat_output = get_stats(array_serial, ecom_ip, InstanceID,
                                        ecom_user, ecom_pass)

    skip_fields = ["EMCSpinUPS", "EMCCurrentPWRSavingLogTimeStamp",
                   "EMCSpinningCounter", "EMCStandbyCounter"]

    process_stats(header_row, stat_output, array_serial, "Disks", skip_fields)


def pool_stats_query(array_serial, ecom_ip, ecom_user="admin",
                      ecom_pass="#1Password"):
   
    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url,(ecom_user,ecom_pass),
                                      default_namespace="/root/emc")

    # Lets locate our array
    array_list = ecom_conn.EnumerateInstanceNames("Clar_StorageSystem")
    array = None

    for i in array_list:
        if i["Name"] == "CLARiiON+%s" % array_serial:
            array = i

    # Walk our pools for stats
    pool_classes = ["EMC_UnifiedStoragePool","EMC_DeviceStoragePool",
                    "EMC_VirtualProvisioningPool"]

    processed_stats = ["TotalManagedSpace","RemainingManagedSpace",
                       "EMCPercentSubscribed","EMCSubscribedCapacity",
                       "EMCEFDCacheEnabled"]
  
    zabbix_data = []
    timestamp = datetime.now().strftime("%s")

    for pool_class in pool_classes:
        for i in ecom_conn.Associators(array,ResultClass=pool_class):
         
            for stat in processed_stats:    
                try:
                    zabbix_key = "emc.vnx.perf.%s[%s]" % (stat,i["InstanceID"].replace(" ","_"))
                    zabbix_data.append("%s %s %s %s" % (array_serial,zabbix_key,timestamp,i[stat]))
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

    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url,(ecom_user,ecom_pass),
                                      default_namespace="/root/emc")

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
    health_classes = ["EMC_LinkControlDevice","EMC_PowerDevice",
                      "EMC_BatteryDevice","EMC_StorageProcessorSystem",
                      "EMC_DiskDrive"]

    for device in health_classes:
        dev_instance = ecom_conn.Associators(array,ResultClass = device)
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
                        help="Collect Stats on Physical Disks")
    group.add_argument('--volumes', '-v', action="store_true",
                        help="Collect Stats on Volumes/LUNs")
    group.add_argument('--procs', '-p', action="store_true",
                        help="Collect Stats on Storage Processors")
    group.add_argument('--pools', '-o', action="store_true",
                        help="Collect Stats on Physical Disks")
    group.add_argument('--array', '-a', action="store_true",
                        help="Collect Stats on Array devices and enclosures")


    args = parser.parse_args()

    array_serial = None
    item = None

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
        sys.exit()


if __name__ == "__main__":
    main()
