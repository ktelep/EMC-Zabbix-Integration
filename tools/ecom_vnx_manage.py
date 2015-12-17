#!/bin/env python

import sys
import json
import pywbem
import argparse


def add_vnx(spa_ip, spb_ip, array_user, array_pass,
            ecom_ip, ecom_user="admin", ecom_pass="#1Password"):

    ecom_url = "https://%s:5989" % ecom_ip
    ecom_conn = pywbem.WBEMConnection(ecom_url,(ecom_user,ecom_pass),
                                      default_namespace="/root/emc")
    ers = ecom_conn.EnumerateInstanceNames("EMC_SystemRegistrationService")
    o = ecom_conn.InvokeMethod("EMCAddSystem",ers[0],
                               ArrayType = pywbem.Uint16(1),
                               Addresses = [spa_ip,spb_ip],
                               Types = [pywbem.Uint16(2),pywbem.Uint16(2)],
                               User = array_user, Password = array_pass 
                             )
  
    results  = ["Success","Not Supported","Unknown","Timeout","Failed",
                "Inavlid Parameter","In Use","Existing"]
    print "Execution Ouput:"
    print o
    print "Result: %s" % results[o[0]]

def main():
   
    parser = argparse.ArgumentParser()
    parser.add_argument("spa_ip", help="IP Address of SPA")
    parser.add_argument("spb_ip", help="IP Address of SPB")
    parser.add_argument("array_user", help="Username for Array")
    parser.add_argument("array_pass", help="Password for Array")
    parser.add_argument("ecom_ip", help="IP Address of ECOM Server")
    parser.add_argument("--ecom_user", help="Username for ECOM Server",
                        default="admin")
    parser.add_argument("--ecom_pass", help="Password for ECOM Server",
                        default="#1Password")


    args = parser.parse_args()

    add_vnx(args.spa_ip, args.spb_ip, args.array_user, args.array_pass,
            args.ecom_ip, args.ecom_user, args.ecom_pass)

if __name__ == "__main__":
    main()

   

