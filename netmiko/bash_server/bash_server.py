import io
import re
import socket
import telnetlib
import time
from collections import deque
from os import path
from threading import Lock

import paramiko
import serial
from tenacity import retry, stop_after_attempt, wait_exponential

from netmiko import log
from netmiko.terminal_server.terminal_server import TerminalServer
from netmiko.netmiko_globals import MAX_BUFFER, BACKSPACE_CHAR
from netmiko.ssh_exception import (
	NetmikoTimeoutException,
	NetmikoAuthenticationException,
)
from netmiko.utilities import (
	write_bytes,
	check_serial_port,
	get_structured_data,
	get_structured_data_genie,
	get_structured_data_ttp,
	select_cmd_verify,
)
from netmiko.utilities import m_exec_time  # noqa


"""Generic Bash Server driver."""
from netmiko.base_connection import BaseConnection


class BashServer(TerminalServer):
	"""Generic Bash Server driver.

	Allow direct write_channel / read_channel operations without session_preparation causing
	an exception.
	"""

	def session_preparation(self):
		"""Do nothing here; base_prompt is not set; paging is not disabled."""
		pass

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
			elif "~]" in prompt or "~>" in prompt:
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


	def set_base_prompt(
		self, pri_prompt_terminator=" ~]$", alt_prompt_terminator=":~>", delay_factor=1
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


class BashServerSSH(BashServer):
	"""Generic Bash Server driver SSH."""

	pass


class BashServerTelnet(BashServer):
	"""Generic Bash Server driver telnet."""

	def telnet_login(self, *args, **kwargs):
		# Disable automatic handling of username and password when using Bash server driver
		pass

	def std_login(self, *args, **kwargs):
		return super().telnet_login(*args, **kwargs)
