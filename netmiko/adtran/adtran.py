import time
import re
from netmiko.cisco_base_connection import CiscoBaseConnection
from netmiko import log
from netmiko.ssh_exception import (
	NetmikoTimeoutException,
	NetmikoAuthenticationException,
)


class AdtranOSBase(CiscoBaseConnection):
	def __init__(self, *args, **kwargs):
			if kwargs.get("global_cmd_verify") is None:
				kwargs["global_cmd_verify"] = False
			return super().__init__(*args, **kwargs)

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		self.ansi_escape_codes = True
		self._test_channel_read()
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
			if "Failure" in prompt:
				self.write_channel(self.RETURN)
				loops += 1
				time_sleep(1)
			if "#" in prompt or ">" in prompt:
				break

		if not prompt:
			raise ValueError(f"Unable to find prompt: {prompt}")
		time.sleep(delay_factor * 0.1)
		self.clear_buffer()
		log.debug(f"[find_prompt()]: prompt is {prompt}")
		return prompt





class AdtranOSSSH(AdtranOSBase):
	pass
