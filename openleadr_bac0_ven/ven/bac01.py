#!/usr/bin/env python3

import BAC0,time,random

from BAC0.core.devices.local.models import (
    analog_output,
    analog_value,
    binary_value,
    character_string
    )

from BAC0.tasks.RecurringTask import RecurringTask 
from bacpypes.primitivedata import Real
import time
import json

import logging


logging.basicConfig(filename='bacnet_app.log', level=logging.ERROR)

# create open ADR point
_new_objects = analog_value(
        name="signal_payload",
        description="Open ADR Payload Signal",
        presentValue=0,is_commandable=False
    )
    
# create open ADR point
_new_objects = analog_value(
        name="int_signal_duration",
        description="Integer Signal Duration",
        presentValue=0,is_commandable=False
    )

# create open ADR point
_new_objects = character_string(
        name="signal_duration",
        description="Signal Duration",
        presentValue="default sig duration"
    )

# create open ADR point
_new_objects = character_string(
        name="signal_start",
        description="Signal Start Time",
        presentValue="default sig duration"

    )


#STATIC_BACNET_IP = '192.168.0.105/24'
STATIC_BACNET_IP = '10.200.200.224/24'
DEVICE_ID = '33333'
bacnet = BAC0.lite(ip=STATIC_BACNET_IP,deviceId=DEVICE_ID)
_new_objects.add_objects_to_application(bacnet)
bacnet._log.info("APP Created Success!")


# function to convert string time to int
def time_to_sec(t):
   h, m, s = map(int, t.split(':'))
   return h * 3600 + m * 60 + s




def updater():

    try:

        #BACnet read on eGauge for total building power
        read_vals = f'10.200.200.196 analogInput 524290 presentValue'
        #read_vals = f'12345:2 analogInput 2 presentValue'
        bacnet._log.info("Excecuting read_vals statement for power meter:", read_vals)
        read_result = bacnet.read(read_vals)
        read_result_round = round((read_result/1000),2)
        bacnet._log.info("Total Watts of power meter:", read_result_round)
        power_meter_dict = { 'kW': read_result_round}

        with open('power_meter_data.json', 'w') as fp:
            json.dump(power_meter_dict, fp)


    except Exception as e:
        logging.error("Unexpected error on meter read:" + str(e))      
    
    try:
    
        '''
        add in fix for strings in BAC0
        '''
    
        with open('event_info.json', 'r') as fp:
            data = json.load(fp)
        bacnet._log.info(f"Event Info: {data}")

    except Exception as e:
        logging.error("Unexpected error on event info read:" + str(e))   


    try:

        with open('event_info.json', 'r') as fp:
            new_payload_dur = json.load(fp)

        new_payload_dur_int = new_payload_dur['duration']
        new_payload_dur_int = time_to_sec(new_payload_dur_int)
        bacnet._log.info(f"Payload Duration from VTN load success: {new_payload_dur_int}")
            
        dr_dur_int = bacnet.this_application.get_object_name(f'int_signal_duration')

        dr_dur_int.presentValue = new_payload_dur_int
        bacnet._log.info(f"new_payload_dur_int is {dr_dur_int.presentValue}")

     
     
    except Exception as e:
        logging.error("Unexpected error setting BACnet duration int:" + str(e))      
        dr_dur_int = bacnet.this_application.get_object_name(f'int_signal_duration')
        dr_dur_int.presentValue = int(0)
        logging.error(f"Resorting int_signal_duration back to: {dr_dur_int.presentValue}")


    try:

        with open('event_signal_payload.json', 'r') as fp:
            new_payload_data = json.load(fp)

        new_payload_data_sig = new_payload_data['signal_payload']
        bacnet._log.info(f"Payload Signal from VTN load success: {new_payload_data_sig}")
            
        dr_sig = bacnet.this_application.get_object_name(f'signal_payload')

        dr_sig.presentValue = new_payload_data_sig
        bacnet._log.info(f"demand_resp_level is {dr_sig.presentValue}")

     
     
    except Exception as e:
        logging.error("Unexpected error setting BACnet sig payload:" + str(e))      
        dr_sig = bacnet.this_application.get_object_name(f'signal_payload')
        dr_sig.presentValue = int(0)
        logging.error(f"Resorting demand_resp_level back to: {dr_sig.presentValue}")


def main():
    task1 = RecurringTask(updater,delay=60)
    task1.start()

    
    while True:
        pass
        
        
if __name__ == '__main__':
    logging.info("Starting main loop")
    try:
        main()
    except Exception as e:
        logging.error("Unexpected error trying to run main loop:" + str(e))
