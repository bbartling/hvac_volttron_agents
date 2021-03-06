This agent will reset a variable volume air handling unit duct pressure setpoint to save fan energy consumption. In the `init` be sure how create a topic for all VAV BACnet controllers and the AHU BACnet controller, these need to be hard coded into the agent.py file. Also each `rpc` call in the `def actuate_point(self):` needs to be hard coded to match the `init` topics for what BACnet controller get a read (VAV box damper positions) or a write (AHU duct pressure setpoint).


See HVAC VAV fan system sequence in the PDF folder - G36_2018 (86850).pdf for how the agent code is supposed to work per ASHREA guidelines. On page 19 Informative Table 5.1.14.4 "Example Sequence T&R Variables" these are the parameters of the agent config file.



First install agent config file to the VOLTTRON platform config store:
`vctl config store platform.trimmeragent config ./AhuTrimRespondAgent/config`


Check platform config store:
`vctl config get platform.trimmeragent config`


Also for debugging purposes I included the `-f` for a `force` if the agent needs to be reinstalled over and over without having to do a `vctl stop agent` then a `vctl remove agent` the `-f` can force a reinstall without the stop and remove vctl process.

Install the agent.  
`python scripts/install-agent.py -s AhuTrimRespondAgent/ -c AhuTrimRespondAgent/config  --tag trimmer -i platform.trimmeragent -f`


At any time after the agent is installed when the agent is running these parameters in the config file can be edited on a live HVAC system for tuning purposes. Call back functions in the agent script will update changed parameters on the live system. 
`vctl config edit platform.trimmeragent config`







