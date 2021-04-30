This agent will reset a variable volume air handling unit duct pressure setpoint to save fan energy consumption. In the `init` be sure how create a topic for all VAV BACnet controllers and the AHU BACnet controller, these need to be hard coded into the agent.py file. Also each `rpc` call needs to be hard coded to reflect what BACnet controller to read or write.


See HVAC VAV fan system sequence in the PDF folder - G36_2018 (86850).pdf Page 19 Informative Table 5.1.14.4 Example Sequence T&R Variables are the parameters of the config file.



First install platform config:
`vctl config store platform.trimmeragent config ./AhuTrimRespondAgent/config`


Check platform config:
`vctl config get platform.trimmeragent config`


Also for debugging purposes I included the `-f` for a `force` if the agent needs to be reinstalled over and over without having to do a `vctl stop agent` then a `vctl remove agent` the `-f` can force a reinstall without the stop and remove vctl process.

Install the agent. 
`python scripts/install-agent.py -s AhuTrimRespondAgent/ -c AhuTrimRespondAgent/config  --tag trimmer -i platform.trimmeragent -f`


At any time after the agent is installed when the agent is running these parameters in the config file can be edited on a live HVAC system for tuning purposes. Call back functions in the agent script will update changed parameters on the live system.
`vctl config edit platform.trimmeragent config`







