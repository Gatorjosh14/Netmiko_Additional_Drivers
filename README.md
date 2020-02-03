# Netmiko_Audiocode_Driver
Repository for files related to Netmiko Library specifically for Audiocode devices, both SSH and Telnet

This driver was designed using the 2.4.2 version of the Netmiko Library by ktbyers, all credit goes to him for an excellent library.

How to install:

*I would first suggest backing up your current ssh_dispatcher.py file (copy and rename ssh_dispatcher_copy.py)

*Simply copy and paste the new netmiko foler to your netmiko folder, select copy and replace which will override the ssh_dispatcher.py file in the root folder and add the newly created "audiocode" folder which contains the driver files.

New Changes (All configurable attributes are detailed in “audiocode_ssh.py”):

•	This supports both 6.6 firmware devices should call the  “audiocode_old_cli” Class in the Connection Handler.
•	This supports both 7.2 firmware devices should call the  “audiocode_ssh” Class in the Connection Handler.
•	Integrated the disabling/enabling Methods of the window page natively into the audiocode driver.  
•	Created a new “save_config” Method for saving device configurations natively.  
•	Created a new “reload_device” Method for saving the device configuration natively. 
•	Created a new “device_terminal_exit” Method for gracefully exiting the device when using a terminal server. 
•	Made further refinements in the code to make it cleaner and efficient.
