from __future__ import unicode_literals
from netmiko.cisco_base_connection import CiscoBaseConnection
from netmiko import log
from netmiko.exceptions import (
	NetmikoTimeoutException,
	NetmikoAuthenticationException,
)
import time
import re


class AdtranOSBase(CiscoBaseConnection):
	def __init__(self, *args, **kwargs):
			if kwargs.get("global_cmd_verify") is None:
				kwargs["global_cmd_verify"] = False
			return super().__init__(*args, **kwargs)

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		self.ansi_escape_codes = True
		self._test_channel_read()
		#This disables log writes to console to avoid driver sync issues.
		if self.check_enable_mode():
			self.write_channel('no events' + '\r')
			self.write_channel('\r')

		self.set_base_prompt()
		self.disable_paging(command="terminal length 0")
		# Clear the read buffer
		time.sleep(0.3 * self.global_delay_factor)
		self.clear_buffer()

	def check_enable_mode(self, check_string="#"):
		return super().check_enable_mode(check_string=check_string)

	def enable(self, cmd="enable", pattern="ssword:", re_flags=re.IGNORECASE):
		"""Enter enable mode.

		:param cmd: Device command to enter enable mode
		:type cmd: str

		:param pattern: pattern to search for indicating device is waiting for password
		:type pattern: str

		:param re_flags: Regular expression flags used in conjunction with pattern
		:type re_flags: int
		"""
		output = ""
		msg = (
			"Failed to enter enable mode. Please ensure you pass "
			"the 'secret' argument to ConnectHandler."
		)
		if not self.check_enable_mode():
			self.write_channel(self.normalize_cmd(cmd))
			try:
				output += self.read_until_prompt_or_pattern(
					pattern=pattern, re_flags=re_flags
				)
				self.write_channel(self.normalize_cmd(self.secret))
				
				# Added ability for failed TACACS Authorization by trying a 2nd time:
				output = ""
				output += self.read_until_prompt_or_pattern(
					pattern=pattern, re_flags=re_flags
				)
				if pattern in output:
					self.write_channel(self.normalize_cmd(self.secret))
					output += self.read_until_prompt()
				
				if not self.check_enable_mode():
					raise ValueError(msg)
			except NetmikoTimeoutException:
				raise ValueError(msg)
		return output


	def exit_enable_mode(self, exit_command="disable"):
		return super().exit_enable_mode(exit_command=exit_command)

	def check_config_mode(self, check_string=")#"):
		return super().check_config_mode(check_string=check_string)

	def config_mode(self, config_command="config term", pattern=""):
		return super().config_mode(config_command=config_command, pattern=pattern)

	def exit_config_mode(self, exit_config="end", pattern="#"):
		return super().exit_config_mode(exit_config=exit_config, pattern=pattern)

	def set_base_prompt(
		self, pri_prompt_terminator=">", alt_prompt_terminator="#", **kwargs
	):
		return super().set_base_prompt(
			pri_prompt_terminator=pri_prompt_terminator,
			alt_prompt_terminator=alt_prompt_terminator,
			**kwargs
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
		max_loops = 20
		loops = 0
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

			# This handles SNMP failure logs that often spam the terminal and incorrectly cause the prompt to be the log error.
			if loops == 20:
				raise ValueError(f"Unable to find prompt: {prompt}")
			elif "Failure" not in prompt and "config" not in prompt and "#" in prompt or ">" in prompt:
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
			cmd_verify=True,
			enter_config_mode=True,
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

			if self.fast_cli and self._legacy_mode:
				for cmd in config_commands:
					self.write_channel(self.normalize_cmd(cmd))
				# Gather output
				output += self._read_channel_timing(
					delay_factor=delay_factor, max_loops=max_loops
				)
			elif not cmd_verify:
				for cmd in config_commands:
					self.write_channel(self.normalize_cmd(cmd))
					time.sleep(delay_factor * 0.05)
				# Gather output - Modified to capture terminal disconnect errors to raise error quicker.
				output += self._read_channel_timing_or_error(
					pattern="Received disconnect",
					delay_factor=delay_factor, 
					max_loops=max_loops
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

			if exit_config_mode:
				output += self.exit_config_mode()
			output = self._sanitize_output(output)
			log.debug(f"{output}")
			return output

	def _read_channel_timing_or_error(self, pattern="", delay_factor=1, max_loops=150):
			"""Read data on the channel based on timing delays.

			Attempt to read channel max_loops number of times. If no data this will cause a 15 second
			delay.

			Once data is encountered read channel for another two seconds (2 * delay_factor) to make
			sure reading of channel is complete.

			:param pattern: the pattern used to identify an error interrupted the read pattern so that \
				quicker resolution can be made before the timeout, preventing long Socket Errors.
			:type pattern: regular expression string

			:param delay_factor: multiplicative factor to adjust delay when reading channel (delays
				get multiplied by this factor)
			:type delay_factor: int or float

			:param max_loops: maximum number of loops to iterate through before returning channel data.
				Will default to be based upon self.timeout.
			:type max_loops: int
			"""
			# Time to delay in each read loop
			loop_delay = 0.1
			final_delay = 2

			# Default to making loop time be roughly equivalent to self.timeout (support old max_loops
			# and delay_factor arguments for backwards compatibility).
			delay_factor = self.select_delay_factor(delay_factor)
			pattern = pattern
			if delay_factor == 1 and max_loops == 150:
				max_loops = int(self.timeout / loop_delay)

			channel_data = ""
			i = 0
			while i <= max_loops:
				time.sleep(loop_delay * delay_factor)
				new_data = self.read_channel()
				if new_data:
					channel_data += new_data
					if pattern in channel_data:
						log.debug(channel_data)
						raise ValueError(f"Error pattern in Read_Channel: '{pattern}'")
				else:
					# Safeguard to make sure really done
					time.sleep(final_delay * delay_factor)
					new_data = self.read_channel()
					if not new_data:
						break
					else:
						channel_data += new_data
						if pattern in channel_data:
							log.debug(channel_data)
							raise ValueError(f"Error pattern in Read_Channel: '{pattern}'")
				i += 1
			return channel_data



class AdtranOSSSH(AdtranOSBase):
	pass

class AdtranOSTelnet(AdtranOSBase):
	def __init__(self, *args, **kwargs):
		default_enter = kwargs.get("default_enter")
		kwargs["default_enter"] = "\r\n" if default_enter is None else default_enter
		super().__init__(*args, **kwargs)
