import paramiko
import time
import re
from netmiko import log
from netmiko.cisco_base_connection import CiscoSSHConnection


# Recommended to only use "send_command_timing" with Vdom enabled devices, prompt mechanism won't work.

class FortinetSSH(CiscoSSHConnection):
	def _modify_connection_params(self):
		"""Modify connection parameters prior to SSH connection."""
		paramiko.Transport._preferred_kex = (
			"diffie-hellman-group14-sha1",
			"diffie-hellman-group-exchange-sha1",
			"diffie-hellman-group-exchange-sha256",
			"diffie-hellman-group1-sha1",
		)

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		delay_factor = self.select_delay_factor(delay_factor=0)
		output = ""

		# If "set post-login-banner enable" is set it will require you to press 'a'
		# to accept the banner before you login. This will accept if it occurs
		count = 1
		while count <= 30:
			output += self.read_channel()
			if "to accept" in output:
				self.write_channel("a\r")
				break
			else:
				time.sleep(0.33 * delay_factor)
			count += 1

		self._test_channel_read()
		self.set_base_prompt()
		self.disable_paging()
		# Clear the read buffer
		time.sleep(0.3 * self.global_delay_factor)
		self.clear_buffer()

	def disable_paging(self, delay_factor=1, **kwargs):
		"""Disable paging is only available with specific roles so it may fail."""
		disable_paging_commands = [
			"config global",
			"config system console",
			"set output standard",
			"end",
			"end"
			]
		output = self.send_config_set(disable_paging_commands,True,.25,150,False,False,None,False,False)
		log.debug("***Window Paging Disabled***")
		return output

	def set_base_prompt(
		self, pri_prompt_terminator="#", alt_prompt_terminator="$", **kwargs):
		"""This insures alt prompts is accounted for"""
		return super().set_base_prompt(
			pri_prompt_terminator=pri_prompt_terminator,
			alt_prompt_terminator=alt_prompt_terminator,
			**kwargs
		)

	def cleanup(self, command="quit"):
		"""Re-enable paging globally."""
		# Return paging state
		enable_paging_commands = ["config global", "config system console", "set output more", "end", "end"]
		# Should test output is valid
		output = self.send_config_set(enable_paging_commands,True,.25,150,False,False,None,False,False)
		log.debug("***Window Paging Enabled***")
		"""Gracefully exit the SSH session."""
		try:
			# The pattern="" forces use of send_command_timing
			if self.check_config_mode(pattern=""):
				self.exit_config_mode()
		except Exception:
			pass
		# Always try to send final 'exit' (command)
		self._session_log_fin = True
		self.write_channel(command + self.RETURN)

	def config_mode(self, config_command=""):
		"""No config mode for Fortinet devices."""
		return ""

	def exit_config_mode(self, exit_config="end", pattern1="#", pattern2="$"):
		"""Exit from configuration mode.
		:param exit_config: Command to exit configuration mode
		:type exit_config: str
		:param pattern: Pattern to terminate reading of channel
		:type pattern: str
		"""
		output = ""
		if pattern1:
			combined_pattern = pattern1
		if pattern2:
			combined_pattern = r"({}|{})".format(pattern1, pattern2)

		if self.check_config_mode():
			self.write_channel(self.normalize_cmd(exit_config))
			output = self.read_until_pattern(pattern=combined_pattern, re_flags=0)
			if self.check_config_mode():
				raise ValueError("Failed to exit configuration mode")
		log.debug("exit_config_mode: {}".format(output))
		return output

	def enable(self):
		"""Enable mode not used in Fortinet"""
		pass

	def check_config_mode(self, check_string1=") #", check_string2 =") $", pattern=""):
		"""Checks if the device is in configuration mode or not.

		:param check_string: Identification of configuration mode from the device
		:type check_string: str

		:param pattern: Pattern to terminate reading of channel
		:type pattern: str
		"""
		self.write_channel(self.RETURN)
		# You can encounter an issue here (on router name changes) prefer delay-based solution
		if not pattern:
			output = self._read_channel_timing()
		else:
			output = self.read_until_pattern(pattern=pattern)
		return check_string1 in output or check_string2 in output

	def save_config(self, *args, **kwargs):
		"""Not Implemented"""
		raise NotImplementedError

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

		# Created parent loop to counter wrong prompts.
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

			# This handles incorrect prompts being chosen for configurations.
			if loops == 20:
				raise ValueError(f"Unable to find prompt: {prompt}")
			elif (") #" not in prompt and ") $" not in prompt) and ("#" in prompt or "$" in prompt):
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

	def _retrieve_output_mode(self):
		"""Save the state of the output mode so it can be reset at the end of the session."""
		reg_mode = re.compile(r"output\s+:\s+(?P<mode>.*)\s+\n")
		output = self.send_command("get system console")
		result_mode_re = reg_mode.search(output)
		if result_mode_re:
			result_mode = result_mode_re.group("mode").strip()
			if result_mode in ["more", "standard"]:
				self._output_mode = result_mode
