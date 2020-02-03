from __future__ import unicode_literals

import time
import re
import os
import hashlib
import io

from netmiko.base_connection import BaseConnection
from netmiko.py23_compat import string_types
from netmiko import log

class AudiocodeSSH(BaseConnection):
	"""Common Methods for IOS (both SSH and telnet)."""

	def session_preparation(self):
		"""Prepare the session after the connection has been established."""
		self._test_channel_read(pattern=r"[>#]")
		self.set_base_prompt()
		self.disable_paging()
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

		:param pri_prompt_terminator: Primary trailing delimiter for identifying a device prompt
		:type pri_prompt_terminator: str

		:param alt_prompt_terminator: Alternate trailing delimiter for identifying a device prompt
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
		"""Check if in enable mode. Return boolean."""
		return super(AudiocodeSSH, self).check_enable_mode(
			check_string=check_string
		)

	def enable(self, cmd="enable", pattern="ssword", re_flags=re.IGNORECASE):
		"""Enter enable mode."""
		return super(AudiocodeSSH, self).enable(
			cmd=cmd, pattern=pattern, re_flags=re_flags
		)

	def exit_enable_mode(self, exit_command="disable"):
		"""Exits enable (privileged exec) mode."""
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
		# You can encounter an issue here (on router name changes) prefer delay-based solution

		if not pattern:
			output = self._read_channel_timing()
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
			output = self.read_until_pattern(pattern=pattern)
			if not self.check_config_mode():
				raise ValueError("Failed to enter configuration mode.")
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

	def save_config(self, cmd="wr", confirm=False, confirm_response=""):
		"""Saves Config Using Copy Run Start"""
		return super(AudiocodeSSH, self).save_config(
			cmd=cmd, confirm=confirm, confirm_response=confirm_response
		)

	def exit_config_mode(self, exit_config="exit", pattern="#"):
		"""Exit from configuration mode."""
		return super(AudiocodeSSH, self).exit_config_mode(
			exit_config=exit_config, pattern=pattern
		)

	def disable_paging(self):
		"""Can't be disabled this way due to enable mode requirement"""
		pass

	def set_terminal_width(self):
		"""Not a configurable parameter"""
		pass

	def disconnect(self):
		"""Try to gracefully close the SSH connection."""
		try:
			self.cleanup()
			if self.protocol == "ssh":
				self.paramiko_cleanup()
			elif self.protocol == "telnet":
				self.remote_conn.close()
			elif self.protocol == "serial":
				self.remote_conn.close()
		except Exception:
			# There have been race conditions observed on disconnect.
			pass
		finally:
			self.remote_conn_pre = None
			self.remote_conn = None
			self.close_session_log()

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
	"""Cisco IOS Telnet driver."""

	pass




