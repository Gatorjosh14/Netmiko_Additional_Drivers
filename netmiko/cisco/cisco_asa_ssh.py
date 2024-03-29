"""Subclass specific to Cisco ASA."""
import re
import time
from netmiko import log
from netmiko.cisco_base_connection import CiscoSSHConnection, CiscoFileTransfer
from netmiko.exceptions import NetmikoAuthenticationException


class CiscoAsaSSH(CiscoSSHConnection):
	"""Subclass specific to Cisco ASA."""

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
			elif "config" not in prompt and ("#" in prompt or ">" in prompt):
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

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		self._test_channel_read()
		self.set_base_prompt()

		if self.secret:
			self.enable()
		else:
			self.asa_login()

		if self.allow_auto_change:
			try:
				self.send_config_set("terminal width 511")
			except ValueError:
				# Don't fail for the terminal width
				pass
		else:
			# Disable cmd_verify if the terminal width can't be set
			self.global_cmd_verify = False

		self.disable_paging(command="terminal pager 0")

		# Clear the read buffer
		time.sleep(0.3 * self.global_delay_factor)
		self.clear_buffer()
	
	def check_config_mode(self, check_string=")#", pattern=r"[>\#]"):
		return super().check_config_mode(check_string=check_string, pattern=pattern)

	def enable(
		self,
		cmd="enable",
		pattern="ssword",
		enable_pattern=r"\#",
		re_flags=re.IGNORECASE,
	):
		return super().enable(
			cmd=cmd, pattern=pattern, enable_pattern=enable_pattern, re_flags=re_flags
		)
		
	def send_command_timing(self, *args, **kwargs):
		"""
		If the ASA is in multi-context mode, then the base_prompt needs to be
		updated after each context change.
		"""
		output = super().send_command_timing(*args, **kwargs)
		if len(args) >= 1:
			command_string = args[0]
		else:
			command_string = kwargs["command_string"]
		if "changeto" in command_string:
			self.set_base_prompt()
		return output

	def send_command(self, *args, **kwargs):
		"""
		If the ASA is in multi-context mode, then the base_prompt needs to be
		updated after each context change.
		"""
		if len(args) >= 1:
			command_string = args[0]
		else:
			command_string = kwargs["command_string"]

		# If changeto in command, look for '#' to determine command is done
		if "changeto" in command_string:
			if len(args) <= 1:
				expect_string = kwargs.get("expect_string", "#")
				kwargs["expect_string"] = expect_string
		output = super().send_command(*args, **kwargs)

		if "changeto" in command_string:
			self.set_base_prompt()

		return output

	def send_command_expect(self, *args, **kwargs):
		"""Backwards compaitibility."""
		return self.send_command(*args, **kwargs)

	def set_base_prompt(self, *args, **kwargs):
		"""
		Cisco ASA in multi-context mode needs to have the base prompt updated
		(if you switch contexts i.e. 'changeto')

		This switch of ASA contexts can occur in configuration mode. If this
		happens the trailing '(config*' needs stripped off.
		"""
		cur_base_prompt = super().set_base_prompt(*args, **kwargs)
		match = re.search(r"(.*)\(conf.*", cur_base_prompt)
		if match:
			# strip off (conf.* from base_prompt
			self.base_prompt = match.group(1)
			return self.base_prompt

	def asa_login(self):
		"""
		Handle ASA reaching privilege level 15 using login

		twb-dc-fw1> login
		Username: admin

		Raises NetmikoAuthenticationException, if we do not reach privilege
		level 15 after 10 loops.
		"""
		delay_factor = self.select_delay_factor(0)

		i = 1
		max_attempts = 10
		self.write_channel("login" + self.RETURN)
		while i <= max_attempts:
			time.sleep(0.5 * delay_factor)
			output = self.read_channel()
			if "sername" in output:
				self.write_channel(self.username + self.RETURN)
			elif "ssword" in output:
				self.write_channel(self.password + self.RETURN)
			elif "#" in output:
				return
			else:
				self.write_channel("login" + self.RETURN)
			i += 1

		msg = "Unable to enter enable mode!"
		raise NetmikoAuthenticationException(msg)

	def save_config(self, cmd="write mem", confirm=False, confirm_response=""):
		"""Saves Config"""
		return super().save_config(
			cmd=cmd, confirm=confirm, confirm_response=confirm_response
		)


class CiscoAsaFileTransfer(CiscoFileTransfer):
	"""Cisco ASA SCP File Transfer driver."""

	pass
