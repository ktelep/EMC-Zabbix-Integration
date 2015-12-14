#!/bin/env python

import csv
import sys
import json
import getopt
import pywbem
import datetime
import StringIO
import tempfile
import subprocess
from datetime import datetime, timedelta

ecom_ip="10.5.36.148"
sender_command = "/usr/local/bin/zabbix_sender"
config_path = "/etc/zabbix_agentd.conf"
sample_interval = 10


def convert_to_local(timestamp):
    """ Convert the CIM timestamp to a local one, correcting for an invalid TZ setting and DST """

    # Convert timestamp to datetime object, stripping UTC offset
    time_stamp = datetime.strptime(timestamp[:-4], "%Y%m%d%H%M%S.%f")
    zone_offset = int(timestamp[-4:])

    # Calculte the time in UTC based on the array's assumed offset
    utc_time = time_stamp - timedelta(minutes=zone_offset)

    # Recalculate time based on current timezone
    offset = datetime.now() - datetime.utcnow()
    local_time = utc_time + offset

    return local_time

def sp_stats_query(array_serial, ecom_ip, ecom_user="admin",
                        ecom_pass="#1Password"):
    """Discover info on disks in the VNX array


       Arguments-
           device_id:     (string) The DeviceID of the disk in the array
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

    SP_Stat_InstanceID = "CLARiiON+%s+EMC_MANIFEST_DEFAULT+FEAdapt" % array_serial

    # Get  
    info = ecom_conn.ExecQuery("DMTF:CQL",
                               "SELECT SampleInterval from CIM_StatisticsCollection where InstanceID='CLARiiON+%s'" % array_serial)
    
    # Determine if the interval if 5 minutes, if not reset it to 10 minutes 
    if sample_interval < 10:
        cim_dt = "00000000000%s00.000000:000" % (str(sample_interval))
    else:
        cim_dt = "0000000000%s00.000000:000" % (str(sample_interval))

    if info[0]["SampleInterval"] != pywbem.CIMDateTime(cim_dt):
        print "Setting interval to %d minutes" % (sample_interval)
        info[0]["SampleInterval"] = pywbem.CIMDateTime(cim_dt)
        ecom_conn.ModifyInstance(info[0],PropertyList=["SampleInterval"])
    
    # Figure out what stats we're gathering
    manifest = ecom_conn.ExecQuery("DMTF:CQL",
                        "SELECT * FROM Clar_Blockmanifest where InstanceID='%s'" % SP_Stat_InstanceID)

    header_row =  manifest[0]["CSVSequence"]

    # Build our CIMInstanceName for the StatsService for THIS array
    stats_service = pywbem.CIMInstanceName("Clar_BlockStatisticsService", 
                                           keybindings=pywbem.NocaseDict({'CreationClassName': 'Clar_BlockStatisticsService',
                                                                   'SystemName':  'CLARiiON+' + array_serial,
                                                                   'Name': 'EMCBlockStatisticsService',
                                                                   'SystemCreationClassName': 'Clar_StorageSystem'}),
                                           namespace='/root/emc')
                                                                           
    stat_output = ecom_conn.InvokeMethod("GetStatisticsCollection",
                                         stats_service,
                                         StatisticsFormat=pywbem.Uint16(2))

    sp_data = stat_output[1]["Statistics"][2]
    f = StringIO.StringIO(sp_data)
    reader = csv.reader(f, delimiter=';')

    timestamp_index = header_row.index("StatisticTime")
    perf_dev_id_index = header_row.index("InstanceID")
    element_type_index = header_row.index("ElementType")

    skip_fields = (timestamp_index,perf_dev_id_index,element_type_index)
    zabbix_data = []

    timestamp = None
    for row in reader:

        timestamp = convert_to_local(row[timestamp_index]).strftime("%s")
        perf_dev_id = row[perf_dev_id_index]

        for i in range(0,len(header_row)):
            if i in skip_fields:
                continue 
            zabbix_key = "emc.vnx.perf.%s[%s]" % (header_row[i], perf_dev_id)
            zabbix_data.append("%s %s %s %s" % (array_serial, zabbix_key, timestamp, row[i]))

    print "------------------------------------------------------"
    print "Current Time: %s    Stat Time: %s" % (datetime.now().strftime("%c"), datetime.fromtimestamp(int(timestamp)).strftime("%c"))
    with open("/tmp/sp_data.tmp","w") as f:
        f.write("\n".join(zabbix_data))

    subprocess.call([sender_command,"-v","-c",config_path,"-s",array_serial,"-T","-i","/tmp/sp_data.tmp"])
    print "------------------------------------------------------\n"


    # These align with the proper entries in Clar_Blockmanifest
    # 0 = Array
    # 1 = Disks
    # 2 = SPs
    # 3 = SP Ports
    # 4 = Snap 
    # 5 = Volumes

if __name__ == "__main__":
    sp_stats_query(sys.argv[1],ecom_ip)

