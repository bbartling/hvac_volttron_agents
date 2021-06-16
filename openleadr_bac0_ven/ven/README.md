Created Date: June 16th 2021

This is for testing open ADR signal type `LOAD_CONTROL` On/Off Control

```
signal_name='LOAD_CONTROL',
signal_type='x-loadControlCapacity',
```

openleadr client VEN app
https://openleadr.org/


that runs along side a BAC0 BACnet app
https://bac0.readthedocs.io/en/latest/


The openleadr VEN app communicates to an openleadr VTN app on cloud
to obtain demand response events pushed to building via open ADR.

The openleadr VEN app saves json files to the working directory that
the BAC0 app will read and publish the data as read only BACnet
points. Building automation or IoT can read the BACnet data
and control building HVAC accordingly for demand response event.


Modify BAC0 app electrical meter reading BACnet device addressing 
as necessary. This works on an eGauge electrical meter, where the BAC0 
app will BACnet read every 60 seconds on this eGauge at IP address of 
10.200.200.196 analogInput 524290 or in the BAC0 code here:

`read_vals = f'10.200.200.196 analogInput 524290 presentValue'`

This meter value comes through in Watts which is divided by 1000
to calculate kW where this value is sent to the VTN as a report value.


tested on Python 3.9
-pip install BAC0
-pip install aiohttp
-pip install aiofiles
-pip install openleadr

Prior to starting building side VEN & BAC0, make sure your VTN app
is running. Then open two terminals in this directory, terminal one:
`python bac01.py`

terminal two:
`python myven.py`


'''
OpenADR 2.0b Profile Specification  - page 32 - Table 1 Signals

This is an instruction for 
the load controller to operate at a level that is 
some percentage of its 
maximum load consumption capacity. This can be 
mapped to specific load 
controllers to do things 
like duty cycling. Note that 
1.0 refers to 100% consumption. In the case of 
simple ON/OFF type devices then 0 = OFF and 1 = ON. 
'''

