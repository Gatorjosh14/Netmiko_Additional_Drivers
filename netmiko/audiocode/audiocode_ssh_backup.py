from __future__ import unicode_literals
from netmiko.base_connection import BaseConnection
from netmiko import log
from netmiko.exceptions import (
	NetmikoTimeoutException,
	NetmikoAuthenticationException,
	ConfigInvalidException,
)
import time
import re


class AudiocodeBaseSSH (BaseConnection):
	"""Common Methods for AudioCodes running 7.2 CLI for SSH."""

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		#self._test_channel_read(pattern=r"[>#]")
		self.set_base_prompt()
		self.disable_paging()
		self.set_terminal_width()
		# Clear the read buffer
		time.sleep(0.3 * self.global_delay_factor)
		self.clear_buffer()

	def set_base_prompt(
		self, pri_prompt_terminator="#", alt_prompt_terminator=">", delay_factor=1
		):
		"""Sets self.base_prompt

		Used as delimiter for stripping of trailing prompt in output.

		Should be set to something that is general and applies in multiple contexts. For Cisco
		devices this will be set to router hostname (i.e. prompt without > or #).

		This will be set on entering user exec or privileged exec on Cisco, but not when
		entering/exiting config mode.

		:param pri_prompt_terminator: Primary trailing delimiter for identifying a device prompt
		:type pri_prompt_terminator: str

		:param alt_prompt_terminator: Alternate trailing delimiter for identifying a device prompt
		:type alt_prompt_terminator: str

		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		"""
		prompt = self.find_prompt(delay_factor=delay_factor)
		pattern = rf"(\*?{pri_prompt_terminator}$|\*?{alt_prompt_terminator})$"
		if not re.search(pattern, prompt):
			raise ValueError(f"Router prompt not found: {repr(prompt)}")
		else:
			# Strip off trailing terminator
			self.base_prompt = re.sub(pattern, "", prompt)
			return self.base_prompt

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
		return check_string in output or ")*#" in output

	def check_enable_mode(self, check_string="#"):
		"""Check if in enable mode. Return boolean.

		:param check_string: Identification of privilege mode from device
		:type check_string: str
		"""
		
		self.write_channel(self.RETURN)
		output = self.read_until_prompt()
		return check_string in output
		
		#return super(AudiocodeBaseSSH, self).check_enable_mode(
		#	check_string=check_string
		#)

	def cleanup(self):
		"""Gracefully exit the SSH session."""
		try:
			self.exit_config_mode()
		except Exception:
			pass
		# Always try to send final 'exit' regardless of whether exit_config_mode works or not.
		self._session_log_fin = True
		self.write_channel("exit" + self.RETURN)

	def enable(self, cmd="enable", pattern="ssword", re_flags=re.IGNORECASE):
		"""Enter enable mode.

		:param cmd: Device command to enter enable mode
		:type cmd: str

		:param pattern: pattern to search for indicating device is waiting for password
		:type pattern: str

		:param re_flags: Regular expression flags used in conjunction with pattern
		:type re_flags: int
		"""
		return super(AudiocodeBaseSSH, self).enable(
			cmd=cmd, pattern=pattern, re_flags=re_flags
		)

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

	def exit_enable_mode(self, exit_command="disable"):
		"""Exit enable mode.

		:param exit_command: Command that exits the session from privileged mode
		:type exit_command: str
		"""
		return super(AudiocodeBaseSSH, self).exit_enable_mode(
			exit_command=exit_command
		)

	def find_prompt(self, delay_factor=1):
		"""Finds the current network device prompt, last line only.

		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		"""
		delay_factor = self.select_delay_factor(delay_factor)
		self.clear_buffer()
		self.write_channel(self.RETURN)
		sleep_time = delay_factor * 0.1
		time.sleep(sleep_time)

		# Created parent loop to counter wrong prompts due to spamming alarm logs into terminal.
		max_loops = 10
		loops = 0
		while loops <= max_loops:
			# Initial attempt to get prompt
			prompt = self.read_channel().strip()
			count = 0
			while count <= 12 and not prompt:
				prompt = self.read_channel().strip()
				if not prompt:
					self.write_channel(self.RETURN)
					time.sleep(sleep_time)
					if sleep_time <= 3:
						# Double the sleep_time when it is small
						sleep_time *= 2
					else:
						sleep_time += 1
				count += 1

			# If multiple lines in the output take the last line
			prompt = self.normalize_linefeeds(prompt)
			prompt = prompt.split(self.RESPONSE_RETURN)[-1]
			prompt = prompt.strip()

			# This verifies a valid prompt has been found before proceeding.
			if loops == 19:
				raise ValueError(f"Unable to find prompt: {prompt}")
			elif "#" in prompt or ">" in prompt:
				break	
			self.write_channel(self.RETURN)
			loops += 1
			time.sleep(1)

		if not prompt:
			raise ValueError(f"Unable to find prompt: {prompt}")
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		log.debug(f"[find_prompt()]: prompt is {prompt}")
		return prompt
			
	def send_config_set(
		self,
		config_commands=None,
		exit_config_mode=True,
		delay_factor=1,
		max_loops=150,
		strip_prompt=False,
		strip_command=False,
		config_mode_command=None,
		cmd_verify=False,
		enter_config_mode=False
	):
		if config_mode_command == None and enter_config_mode == True:
			raise ValueError("For this driver config_mode_command must be specified")
	
		else:
			return super(AudiocodeBaseSSH, self).send_config_set(
				config_commands=config_commands,
				exit_config_mode=exit_config_mode,
				delay_factor=delay_factor,
				max_loops=max_loops,
				strip_prompt=strip_prompt,
				strip_command=strip_command,
				config_mode_command=config_mode_command,
				cmd_verify=cmd_verify,
				enter_config_mode=enter_config_mode
			)

	def disable_paging(
		self, 
		disable_window_config = ["config system","cli-settings","window-height 0","exit"],
		delay_factor=.5
	):
		"""This is designed to disable window paging which prevents paged command 
		output from breaking the script.
		
		:param disable_window_config: Command, or list of commands, to execute.
		:type disable_window_config: str
		
		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		
		"""
		self.enable()
		delay_factor = self.select_delay_factor(delay_factor)
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		disable_window_config = disable_window_config
		log.debug("In disable_paging")
		self.send_config_set(disable_window_config,True,.25,150,False,False,None,False,False)
		log.debug("Exiting disable_paging")
	
	def _enable_paging(
		self, 
		enable_window_config = ["config system","cli-settings","window-height automatic","exit"],
		delay_factor=.5
	):
		"""This is designed to reenable window paging.
		
		:param enable_window_config: Command, or list of commands, to execute.
		:type enable_window_config: str
		
		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		
		"""
		self.enable()
		delay_factor = self.select_delay_factor(delay_factor)
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		enable_window_config = enable_window_config
		log.debug("In _enable_paging")
		self.send_config_set(enable_window_config,True,.25,150,False,False,None,False,False)
		log.debug("Exiting _enable_paging")

	def save_config(self, cmd="write", confirm=False, confirm_response="done"):
		"""Saves the running configuration.
		
		:param cmd: Command to save configuration
		:type cmd: str
		
		:param confirm: Command if confirmation prompt is required
		:type confirm: bool

		:param confirm_response: Command if confirm response required to further script
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
		
	def _reload_device(self, reload_device=True, reload_save=True, cmd_save="reload now", cmd_no_save="reload without-saving"):
		"""Reloads the device.
		
		:param reload_device: Boolean to determine if reload should occur.
		:type reload_device: bool
		
		:param reload_device: Boolean to determine if reload with saving first should occur.
		:type reload_device: bool
		
		:param cmd_save: Command to reload device with save.  Options are "reload now" and "reload if-needed".
		:type cmd_save: str
		
		:param cmd_no_save: Command to reload device.  Options are "reload without-saving", "reload without-saving in [minutes]".
		:type cmd_no_save: str

		"""
		self.enable()
		if reload_device == True and reload_save == True:
			self._enable_paging()
			output = self.send_command_timing(command_string=cmd_save)		
		elif reload_device == True and reload_save == False:
			output = self.send_command_timing(command_string=cmd_no_save)
		else:
			output = "***Reload not performed***"
		return (output)			

	def _device_terminal_exit(self):
		"""This is for accessing devices via terminal. It first reenables window paging for
		future use and exits the device before you send the disconnect method"""
		
		self.enable()
		self._enable_paging()
		output = self.send_command_timing('exit')
		log.debug("_device_terminal_exit executed")
		return (output)

	def set_terminal_width(self):
		"""Not a configurable parameter"""
		pass


class AudiocodeBaseTelnet(AudiocodeBaseSSH):
	"""Audiocode Telnet driver."""
	pass

	
class Audiocode66SSH(AudiocodeBaseSSH):
	"""Audiocode this applies to 6.6 Audiocode Firmware versions."""

	def disable_paging(
		self, 
		disable_window_config = ["config system","cli-terminal","set window-height 0","exit"],
		delay_factor=.5
	):
		"""This is designed to disable window paging which prevents paged command 
		output from breaking the script.
				
		:param disable_window_config: Command, or list of commands, to execute.
		:type disable_window_config: str
			
		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		
		"""		
		return super(Audiocode66SSH, self).disable_paging(
			disable_window_config=disable_window_config, delay_factor=delay_factor
		)
		
	def _enable_paging(
		self, 
		enable_window_config = ["config system","cli-terminal","set window-height 100","exit"],
		delay_factor=.5
	):
		"""This is designed to reenable window paging
		
		:param enable_window_config: Command, or list of commands, to execute.
		:type enable_window_config: str
		
		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		
		"""
		return super(Audiocode66SSH, self)._enable_paging(
			enable_window_config=enable_window_config, delay_factor=delay_factor
		)


class Audiocode66Telnet(Audiocode66SSH):
	"""Audiocode Telnet driver."""
	pass


class AudiocodeShellSSH(AudiocodeBaseSSH):
	"""Audiocode this applies to 6.6 Audiocode Firmware versions that only use the Shell."""
	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		self.write_channel(self.RETURN)
		self.write_channel(self.RETURN)
		self._test_channel_read(pattern="/>")
		self.set_base_prompt()
		# Clear the read buffer
		time.sleep(0.3 * self.global_delay_factor)
		self.clear_buffer()

	def find_prompt(self, delay_factor=1):
		"""Finds the current network device prompt, last line only.

		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		"""
		delay_factor = self.select_delay_factor(delay_factor)
		self.clear_buffer()
		self.write_channel(self.RETURN)
		sleep_time = delay_factor * 0.1
		time.sleep(sleep_time)

		# Created parent loop to counter wrong prompts due to spamming alarm logs into terminal.
		max_loops = 20
		loops = 0
		prompt = ""
		while loops <= max_loops:
			# Initial attempt to get prompt
			prompt = self.read_channel().strip()

			# Check if the only thing you received was a newline
			count = 0
			while count <= 12 and not prompt:
				prompt = self.read_channel().strip()
				if not prompt:
					self.write_channel(self.RETURN)
					time.sleep(sleep_time)
					if sleep_time <= 3:
						# Double the sleep_time when it is small
						sleep_time *= 2
					else:
						sleep_time += 1
				count += 1

			# If multiple lines in the output take the last line
			prompt = self.normalize_linefeeds(prompt)
			prompt = prompt.split(self.RESPONSE_RETURN)[-1]
			prompt = prompt.strip()

			# This verifies a valid prompt has been found before proceeding.
			if loops == 20:
				raise ValueError(f"Unable to find prompt: {prompt}")
			elif "/>" in prompt:
				break	
			self.write_channel(self.RETURN)
			loops += 1
			time.sleep(1)

		if not prompt:
			raise ValueError(f"Unable to find prompt: {prompt}")
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		log.debug(f"[find_prompt()]: prompt is {prompt}")
		return prompt

	def set_base_prompt(self, pri_prompt_terminator="/>", delay_factor=1):
		"""Sets self.base_prompt

		Used as delimiter for stripping of trailing prompt in output.

		Should be set to something that is general and applies in multiple contexts. For Cisco
		devices this will be set to router hostname (i.e. prompt without > or #).

		This will be set on entering user exec or privileged exec on Cisco, but not when
		entering/exiting config mode.

		:param pri_prompt_terminator: Primary trailing delimiter for identifying a device prompt
		:type pri_prompt_terminator: str

		:param delay_factor: See __init__: global_delay_factor
		:type delay_factor: int
		"""
		prompt = self.find_prompt(delay_factor=delay_factor)
		pattern = pri_prompt_terminator
		if not re.search(pattern, prompt):
			raise ValueError(f"Router prompt not found: {repr(prompt)}")
		else:
			# Strip off trailing terminator
			self.base_prompt = prompt
			return self.base_prompt

	def enable(self, cmd="", pattern="", re_flags=re.IGNORECASE):
		"""Enter enable mode."""
		pass

	def exit_enable_mode(self, exit_command=""):
		"""Not in use"""
		pass

	def cleanup(self):
		"""Gracefully exit the SSH session."""
		try:
			self.exit_config_mode()
		except Exception:
			pass
		# Always try to send final 'exit' regardless of whether exit_config_mode works or not.
		self._session_log_fin = True
		self.write_channel("exit" + self.RETURN)

	def send_config_set(
		self,
		config_commands=None,
		exit_config_mode=True,
		delay_factor=1,
		max_loops=150,
		strip_prompt=False,
		strip_command=False,
		config_mode_command=None,
		cmd_verify=False,
		enter_config_mode=False,
		error_pattern="",
	):
		"""
		Send configuration commands down the SSH channel.

		config_commands is an iterable containing all of the configuration commands.
		The commands will be executed one after the other.

		Automatically exits/enters configuration mode.

		:param config_commands: Multiple configuration commands to be sent to the device
		:type config_commands: list or string

		:param exit_config_mode: Determines whether or not to exit config mode after complete
		:type exit_config_mode: bool

		:param delay_factor: Factor to adjust delays
		:type delay_factor: int

		:param max_loops: Controls wait time in conjunction with delay_factor (default: 150)
		:type max_loops: int

		:param strip_prompt: Determines whether or not to strip the prompt
		:type strip_prompt: bool

		:param strip_command: Determines whether or not to strip the command
		:type strip_command: bool

		:param config_mode_command: The command to enter into config mode
		:type config_mode_command: str

		:param cmd_verify: Whether or not to verify command echo for each command in config_set
		:type cmd_verify: bool

		:param enter_config_mode: Do you enter config mode before sending config commands
		:type exit_config_mode: bool

		:param error_pattern: Regular expression pattern to detect config errors in the
		output.
		:type error_pattern: str
		"""
		delay_factor = self.select_delay_factor(delay_factor)
		if config_commands is None:
			return ""
		elif isinstance(config_commands, str):
			config_commands = (config_commands,)

		if not hasattr(config_commands, "__iter__"):
			raise ValueError("Invalid argument passed into send_config_set")

		# Send config commands
		output = ""
		if enter_config_mode:
			cfg_mode_args = (config_mode_command,) if config_mode_command else tuple()
			output += self.config_mode(*cfg_mode_args)

		# If error_pattern is perform output gathering line by line and not fast_cli mode.
		if self.fast_cli and self._legacy_mode and not error_pattern:
			for cmd in config_commands:
				self.write_channel(self.normalize_cmd(cmd))
			# Gather output
			output += self._read_channel_timing(
				delay_factor=delay_factor, max_loops=max_loops
			)

		elif not cmd_verify:
			for cmd in config_commands:
				self.write_channel(self.normalize_cmd(cmd))
				time.sleep(delay_factor * 2)

				# Gather the output incrementally due to error_pattern requirements
				if error_pattern:
					output += self._read_channel_timing(
						delay_factor=delay_factor, max_loops=max_loops
					)
					if re.search(error_pattern, output, flags=re.M):
						msg = f"Invalid input detected at command: {cmd}"
						raise ConfigInvalidException(msg)

			# Standard output gathering (no error_pattern)
			if not error_pattern:
				output += self._read_channel_timing(
					delay_factor=delay_factor, max_loops=max_loops
				)

		else:
			for cmd in config_commands:
				self.write_channel(self.normalize_cmd(cmd))

				# Make sure command is echoed
				new_output = self.read_until_pattern(pattern=re.escape(cmd.strip()))
				output += new_output

				# We might capture next prompt in the original read
				pattern = f"(?:{re.escape(self.base_prompt)}|#)"
				if not re.search(pattern, new_output):
					# Make sure trailing prompt comes back (after command)
					# NX-OS has fast-buffering problem where it immediately echoes command
					# Even though the device hasn't caught up with processing command.
					new_output = self.read_until_pattern(pattern=pattern)
					output += new_output

				if error_pattern:
					if re.search(error_pattern, output, flags=re.M):
						msg = f"Invalid input detected at command: {cmd}"
						raise ConfigInvalidException(msg)

		if exit_config_mode:
			output += self.exit_config_mode()
		output = self._sanitize_output(output)
		log.debug(f"{output}")
		return output

	def check_config_mode(self, check_string="/CONFiguration", pattern=""):
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
		return check_string in output

	def exit_config_mode(self, exit_config="..", pattern="/>"):
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

	def _save_config(self, 
		cmd="SaveConfiguration", 
		confirm=False, 
		confirm_response="Configuration has been saved"
		):
		"""Saves the running configuration.
		
		:param cmd: Command to save configuration
		:type cmd: str
		
		:param confirm: Command if confirmation prompt is required
		:type confirm: bool

		:param confirm_response: Command if confirm response required to further script
		:type confirm response: str
		
		"""
		return super(AudiocodeShellSSH, self)._save_config(
			cmd=cmd, confirm=confirm, confirm_response=confirm_response
		)
		
	def _reload_device(self, 
		reload_device=True, 
		reload_save=True, 
		cmd_save="SaveAndReset", 
		cmd_no_save="ReSetDevice",
		reload_message="Resetting the board"
		):
		"""Reloads the device.
		
		:param reload_device: Boolean to determine if reload should occur.
		:type reload_device: bool
		
		:param reload_device: Boolean to determine if reload with saving first should occur.
		:type reload_device: bool
		
		:param cmd_save: Command to reload device with save.  Options are "reload now" and "reload if-needed".
		:type cmd_save: str
		
		:param cmd_no_save: Command to reload device.  Options are "reload without-saving", "reload without-saving in [minutes]".
		:type cmd_no_save: str

		:param reload_message: This is the pattern by which the reload is detected.
		:type reload_message: str

		"""
		if reload_device == True and reload_save == True:
			self.write_channel(cmd_save + self.RETURN)
			output = self.read_until_pattern(pattern=reload_message)
			try:
				self.write_channel("exit" + self.RETURN)
			except:
				pass
		elif reload_device == True and reload_save == False:
			self.write_channel(cmd_no_save + self.RETURN)
			output = self.read_until_pattern(pattern=reload_message)
			try:
				self.write_channel("exit" + self.RETURN)
			except:
				pass
		else:
			raise ValueError("***Reload not performed***")
		return (output)			

	def _device_terminal_exit(self):
		"""This is for accessing devices via terminal. It first reenables window paging for
		future use and exits the device before you send the disconnect method"""
		
		output = self.send_command_timing('exit')
		return (output)

	def _enable_paging(self):
		"""Not in use"""
		pass
	
class AudiocodeShellTelnet(AudiocodeShellSSH):
	"""Audiocode this applies to 6.6 Audiocode Firmware versions that only use the Shell."""
	pass





