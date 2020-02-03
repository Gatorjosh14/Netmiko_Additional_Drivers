from __future__ import unicode_literals
from netmiko.base_connection import BaseConnection
from netmiko.py23_compat import string_types
from netmiko import log

import time
import re
import os
import hashlib
import io



class AudiocodeSSH (BaseConnection):
	"""Common Methods for AudioCodes running 7.2 CLI (both SSH and telnet)."""

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		self._test_channel_read(pattern=r"[>#]")
		self.set_base_prompt()
		self.disable_window_paging()
		self.set_terminal_width()
		# Clear the read buffer
		time.sleep(0.3 * self.global_delay_factor)
		self.clear_buffer()

	def set_base_prompt(self, pri_prompt_terminator1=">", pri_prompt_terminator2="#", alt_prompt_terminator1="*>",
		alt_prompt_terminator2="*#", delay_factor=1):
		"""Sets self.base_prompt

		Used as delimiter for stripping of trailing prompt in output.

		Should be set to something that is general and applies in multiple contexts. For Cisco
		devices this will be set to router hostname (i.e. prompt without > or #).

		This will be set on entering user exec or privileged exec on Cisco, but not when
		entering/exiting config mode.

		:param pri_prompt_terminator1: Primary trailing delimiter for identifying a device prompt
		:type pri_prompt_terminator: str
		
		:param pri_prompt_terminator2: Primary trailing delimiter for identifying a device prompt
		:type pri_prompt_terminator: str

		:param alt_prompt_terminator1: Alternate trailing delimiter for identifying a device prompt
		when pending config changes are present.
		:type alt_prompt_terminator: str
		
		:param alt_prompt_terminator2: Alternate trailing delimiter for identifying a device prompt
		when pending config changes are present.
		:type alt_prompt_terminator: str

		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		"""
		prompt = self.find_prompt(delay_factor=delay_factor)
		if not prompt[-2] in (alt_prompt_terminator1,alt_prompt_terminator2):
			if not prompt[-1] in (pri_prompt_terminator1,pri_prompt_terminator2):
				raise ValueError("Router prompt not found: {0}".format(repr(prompt)))
		# Strip off trailing terminator
		if alt_prompt_terminator1 or alt_prompt_terminator2 in prompt:
			self.base_prompt = prompt[:-2]
		else:
			self.base_prompt = prompt[:-1]
		return self.base_prompt

	def check_enable_mode(self, check_string="#"):
		"""Check if in enable mode. Return boolean.

		:param check_string: Identification of privilege mode from device
		:type check_string: str
		"""
		return super(AudiocodeSSH, self).check_enable_mode(
			check_string=check_string
		)

	def enable(self, cmd="enable", pattern="ssword", re_flags=re.IGNORECASE):
		"""Enter enable mode.

		:param cmd: Device command to enter enable mode
		:type cmd: str

		:param pattern: pattern to search for indicating device is waiting for password
		:type pattern: str

		:param re_flags: Regular expression flags used in conjunction with pattern
		:type re_flags: int
		"""
		return super(AudiocodeSSH, self).enable(
			cmd=cmd, pattern=pattern, re_flags=re_flags
		)

	def exit_enable_mode(self, exit_command="disable"):
		"""Exit enable mode.

		:param exit_command: Command that exits the session from privileged mode
		:type exit_command: str
		"""
		return super(AudiocodeSSH, self).exit_enable_mode(
			exit_command=exit_command
		)

	def check_config_mode(self, check_string=")#", pattern="#"):
		"""Checks if the device is in configuration mode or not.

		:param check_string: Identification of configuration mode from the device
		:type check_string: str

		:param pattern: Pattern to terminate reading of channel
		:type pattern: str
		"""
		self.write_channel(self.RETURN)
		# If the first check_string value is not valid, it applies the second.

		if not pattern:
			output = self._read_channel_timing(3)
		else:
			output = self.read_until_pattern(pattern=pattern)

		if check_string in output:
			return check_string in output
		else:
			check_string = ")*#"
			return check_string in output

	def config_mode(self, config_command="", pattern=""):
		"""Enter into config_mode.

		:param config_command: Configuration command to send to the device
		:type config_command: str

		:param pattern: Pattern to terminate reading of channel
		:type pattern: str
		"""
		output = ""
		if not self.check_config_mode():
			self.write_channel(self.normalize_cmd(config_command))
			time.sleep(1)
			output = self.read_until_pattern(pattern=pattern)
			if not self.check_config_mode():
				raise ValueError("Failed to enter configuration mode.")
		return output

	def exit_config_mode(self, exit_config="exit", pattern="#"):
		"""Exit from configuration mode.

		:param exit_config: Command to exit configuration mode
		:type exit_config: str

		:param pattern: Pattern to terminate reading of channel
		:type pattern: str
		"""
		output = ""
		if self.check_config_mode():
			self.write_channel(self.normalize_cmd(exit_config))
			output = self.read_until_pattern(pattern=pattern)
			if self.check_config_mode():
				raise ValueError("Failed to exit configuration mode")
		log.debug("exit_config_mode: {}".format(output))
		return output
	
	def cleanup(self):
		"""Gracefully exit the SSH session."""
		try:
			self.exit_config_mode()
		except Exception:
			pass
		# Always try to send final 'exit' regardless of whether exit_config_mode works or not.
		self._session_log_fin = True
		self.write_channel("exit" + self.RETURN)

	def disable_window_paging(
		self, 
		delay_factor=1,
		disable_window_config = ["cli-settings","window-height 0","exit"]
	):
		"""This is designed to disable window paging which prevents paged command output
		from breaking the script"""
		
		delay_factor = self.select_delay_factor(delay_factor)
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		disable_window_config = disable_window_config
		log.debug("In disable_paging")
		log.debug(f"Commands: {disable_window_config}")
		self.send_config_set(disable_window_config,True,.25,150,False,False,"config system")
		log.debug("Exiting disable_paging")

		
	def enable_window_paging(
		self, 
		delay_factor=1,
		enable_window_config = ["cli-settings","window-height automatic","exit"]
	):
		"""This is designed to reenable window paging"""
		delay_factor = self.select_delay_factor(delay_factor)
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		enable_window_config = enable_window_config
		log.debug("In enable_paging")
		log.debug(f"Commands: {enable_window_config}")
		self.send_config_set(enable_window_config,True,.25,150,False,False,"config system")
		log.debug("Exiting enable_paging")

	def save_config(self, cmd="write", confirm=False, confirm_response=""):
		"""Saves the running configuration
		
		:param cmd: Command to save configuration
		:type cmd: str
		
		:param confirm: Command if confirmation prompt is required
		:type confirm: bool

		:param confirm_response: Command if confirm response required to further script
		:type confirm response: str
		
		:param confirm_response: Pattern to terminate reading of channel
		:type confirm response: str
		
		"""
		self.enable()
		if confirm:
			output = self.send_command_timing(command_string=cmd)
			if confirm_response:
				output += self.send_command_timing(confirm_response)
			else:
				# Send enter by default
				output += self.send_command_timing(self.RETURN)
		else:
			# Some devices are slow so match on trailing-prompt if you can
			output = self.send_command(command_string=cmd)

		return (output)
		
	def reload_device(self, reload_device=True, reload_save=True, cmd_save="reload now", cmd_no_save="reload without-saving"):
		"""Saves the running configuration
		
		:param reload_device: Boolean to determine if reload should occur.
		:type reload_device: bool
		
		:param reload_device: Boolean to determine if reload with saving first should occur.
		:type reload_device: bool
		
		:param cmd_save: Command to reload device with save.  Options are "reload now" and "reload if-needed".
		:type cmd_save: str
		
		:param cmd_no_save: Command to reload device.  Options are "reload without-saving", "reload without-saving in [minutes]".
		:type cmd_no_save: str

		"""
		self.reload_device = reload_device
		self.reload_save = reload_save
		self.cmd_save = cmd_save
		self.cmd_no_save = cmd_no_save
		self.enable()
		
		if reload_device == True and reload_save == True:
			self.enable_window_paging()
			output = self.send_command(command_string=cmd_save)		
		elif reload_device == True and reload_save == False:
			output = self.send_command(command_string=cmd_no_save)
		else:
			output = "***Reload not performed***"
		
		return (output)			


	def device_terminal_exit(self):
		"""This is for accessing devices via terminal. It first reenables window paging for
		future use and exits the device before you send the disconnect method"""
		self.enable_window_paging()
		output = self.send_command_timing('exit')
		return (output)

	def set_terminal_width(self):
		"""Not a configurable parameter"""
		pass

	def telnet_login(
		self,
		pri_prompt_terminator1=">",
		pri_prompt_terminator2="#",
		alt_prompt_terminator1="*>",
		alt_prompt_terminator2="*#",
		username_pattern=r"(?:user:|username|login|user name)",
		pwd_pattern=r"assword",
		delay_factor=1,
		max_loops=20,
	):
		"""Telnet login. Can be username/password or just password."""
		delay_factor = self.select_delay_factor(delay_factor)
		time.sleep(1 * delay_factor)

		output = ""
		return_msg = ""
		i = 1
		while i <= max_loops:
			try:
				output = self.read_channel()
				return_msg += output

				# Search for username pattern / send username
				if re.search(username_pattern, output, flags=re.I):
					self.write_channel(self.username + self.TELNET_RETURN)
					time.sleep(1 * delay_factor)
					output = self.read_channel()
					return_msg += output

				# Search for password pattern / send password
				if re.search(pwd_pattern, output, flags=re.I):
					self.write_channel(self.password + self.TELNET_RETURN)
					time.sleep(0.5 * delay_factor)
					output = self.read_channel()
					return_msg += output
					if re.search(
							pri_prompt_terminator, output, flags=re.M
					) or re.search(alt_prompt_terminator, output, flags=re.M):
						return return_msg

				# Support direct telnet through terminal server
				if re.search(r"initial configuration dialog\? \[yes/no\]: ", output):
					self.write_channel("no" + self.TELNET_RETURN)
					time.sleep(0.5 * delay_factor)
					count = 0
					while count < 15:
						output = self.read_channel()
						return_msg += output
						if re.search(r"ress RETURN to get started", output):
							output = ""
							break
						time.sleep(2 * delay_factor)
						count += 1

				# Check for device with no password configured
				if re.search(r"assword required, but none set", output):
					self.remote_conn.close()
					msg = "Login failed - Password required, but none set: {}".format(
						self.host
					)
					raise NetMikoAuthenticationException(msg)

				# Check if proper data received
				if re.search(pri_prompt_terminator1, output, flags=re.M) or re.search(pri_prompt_terminator2, output, flags=re.M) or re.search(
						alt_prompt_terminator1, output, flags=re.M) or re.search(alt_prompt_terminator1, output, flags=re.M):
					return return_msg

				self.write_channel(self.TELNET_RETURN)
				time.sleep(0.5 * delay_factor)
				i += 1
			except EOFError:
				self.remote_conn.close()
				msg = "Login failed: {}".format(self.host)
				raise NetMikoAuthenticationException(msg)

		# Last try to see if we already logged in
		self.write_channel(self.TELNET_RETURN)
		time.sleep(0.5 * delay_factor)
		output = self.read_channel()
		return_msg += output
		if re.search(pri_prompt_terminator1, output, flags=re.M) or re.search(pri_prompt_terminator2, output,flags=re.M) or re.search(
				alt_prompt_terminator1, output, flags=re.M) or re.search(alt_prompt_terminator1, output, flags=re.M):
			return return_msg

		self.remote_conn.close()
		msg = "Login failed: {}".format(self.host)
		raise NetMikoAuthenticationException(msg)





class AudiocodeTelnet(AudiocodeSSH):
	"""Audiocode Telnet driver."""

	pass
	
	
	
class AudiocodeOldCLI(BaseConnection):
	"""Audiocode Old CLI driver."""

	pass




