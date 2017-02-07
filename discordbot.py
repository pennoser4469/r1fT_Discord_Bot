import discord
import asyncio
from discord.ext import commands
import random
import time

#import sys
#sys.stdout = open('bot.log', 'w')


if not discord.opus.is_loaded():
	discord.opus.load_opus('libopus.so')

class VoiceEntry:
	def __init__(self, message, player):
		self.requester = message.author
		self.channel = message.channel
		self.player = player

	def __str__(self):
		fmt = '*{0.title}* uploaded by {0.uploader} and requested by {1.display_name}'
		duration = self.player.duration
		if duration:
			fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
		return fmt.format(self.player, self.requester)

class VoiceState:
	def __init__(self, bot):
		self.current = None
		self.voice = None
		self.bot = bot
		self.play_next_song = asyncio.Event()
		self.songs = asyncio.Queue()
		self.skip_votes = set() # a set of user_ids that voted
		self.audio_player = self.bot.loop.create_task(self.audio_player_task())

	def is_playing(self):
		if self.voice is None or self.current is None:
			return False
		player = self.current.player
		return not player.is_done()

	@property
	def player(self):
		return self.current.player

	def skip(self):
		self.skip_votes.clear()
		if self.is_playing():
			self.player.stop()

	def toggle_next(self):
		self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

	async def audio_player_task(self):
		while True:
			self.play_next_song.clear()
			self.current = await self.songs.get()
			#await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
			self.current.player.start()
			await self.play_next_song.wait()

class Music:
	def __init__(self, bot):
		self.bot = bot
		self.voice_states = {}


	def get_voice_state(self, server):
		state = self.voice_states.get(server.id)
		if state is None:
			state = VoiceState(self.bot)
			self.voice_states[server.id] = state

		return state

	async def create_voice_client(self, channel):
		voice = await self.bot.join_voice_channel(channel)
		state = self.get_voice_state(channel.server)
		state.voice = voice

	def __unload(self):
		for state in self.voice_states.values():
			try:
				state.audio_player.cancel()
				if state.voice:
					self.bot.loop.create_task(state.voice.disconnect())
			except:
				pass

	@commands.command(pass_context=True, no_pm=True)
	async def join(self, ctx):
		"""Summons the bot to join your voice channel."""
		summoned_channel = ctx.message.author.voice_channel
		if summoned_channel is None:
			devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
			await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Was not in a Voice Channel While Trying to Play Music```')
			await self.bot.send_message(ctx.message.author, 'You are not in a voice Channel')
			await bot.delete_message(ctx.message)
			return False

		state = self.get_voice_state(ctx.message.server)
		if state.voice is None:
			state.voice = await self.bot.join_voice_channel(summoned_channel)
		else:
			await state.voice.move_to(summoned_channel)
		await bot.delete_message(ctx.message)

		return True

	@commands.command(pass_context=True, no_pm=True)
	async def play(self, ctx, *, song : str):
		"""Plays a song.
		If there is a song currently in the queue, then it is
		queued until the next song is done playing.
		This command automatically searches as well from YouTube.
		The list of supported sites can be found here:
		https://rg3.github.io/youtube-dl/supportedsites.html
		"""
		state = self.get_voice_state(ctx.message.server)
		opts = {
			'default_search': 'auto',
			'quiet': True
		}

		if state.voice is None:
			success = await ctx.invoke(self.join)
			if not success:
				return

		try:
			player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
		except Exception as e:
			fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
			devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
			await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Error While Playing File```')
			await self.bot.send_message(ctx.message.author, fmt.format(type(e).__name__, e))
		else:
			player.volume = 0.6
			entry = VoiceEntry(ctx.message, player)
			devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
			await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Enqueed ' + str(entry) + '```')
			await self.bot.send_message(ctx.message.author, 'Enqueued ' + str(entry))
			await state.songs.put(entry)
		await bot.delete_message(ctx.message)

	@commands.command(pass_context=True, no_pm=True)
	async def volume(self, ctx, value : int):
		"""Sets the volume of the currently playing song."""

		state = self.get_voice_state(ctx.message.server)
		for r in ctx.message.author.roles:
			if r is discord.utils.get(ctx.message.server.roles, name="@admin"):
				rolepermission = 1
			elif r is discord.utils.get(ctx.message.server.roles, name="@owner"):
				rolepermission = 1
		if rolepermission is 1:
			if state.is_playing():
				player = state.player
				player.volume = value / 100
				devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
				await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Set Volume to ' + format(player.volume) + '```')
				await self.bot.send_message(ctx.message.author, 'Set the volume to {:.0%}'.format(player.volume))
		await bot.delete_message(ctx.message)

	@commands.command(pass_context=True, no_pm=True)
	async def stop(self, ctx):
		"""Stops playing audio and leaves the voice channel.
		This also clears the queue.
		"""
		server = ctx.message.server
		state = self.get_voice_state(server)

		for r in ctx.message.author.roles:
			if r is discord.utils.get(ctx.message.server.roles, name="@admin"):
				rolepermission = 1
			elif r is discord.utils.get(ctx.message.server.roles, name="@owner"):
				rolepermission = 1
		if rolepermission is 1:

			if state.is_playing():
				player = state.player
				player.stop()

			try:
				state.audio_player.cancel()
				del self.voice_states[server.id]
				await state.voice.disconnect()
			except:
				pass
		await bot.delete_message(ctx.message)

	@commands.command(pass_context=True, no_pm=True)
	async def skip(self, ctx):
		"""Vote to skip a song. The song requester can automatically skip.
		3 skip votes are needed for the song to be skipped.
		"""

		state = self.get_voice_state(ctx.message.server)
		if not state.is_playing():
			await self.bot.send_message(ctx.message.author, 'Not playing any music right now...')
			return

		voter = ctx.message.author
		if voter == state.current.requester:
			devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
			await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Skipped Song```')
			await self.bot.send_message(ctx.message.author, 'Requester requested skipping song...')
			state.skip()
		elif voter.id not in state.skip_votes:
			state.skip_votes.add(voter.id)
			total_votes = len(state.skip_votes)
			if total_votes >= 3:
				devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
				await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Skip vote Passed Skipping Song```')
				await self.bot.send_message(ctx.message.author, 'Skip vote passed, skipping song...')
				state.skip()
			else:
				devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
				await self.bot.send_message(devchannel, ctx.message.author.name + ' ```Added a Skip Vote```')
				await self.bot.send_message(ctx.message.author, 'Skip vote added, currently at [{}/3]'.format(total_votes))
		else:
			await self.bot.send_message(ctx.message.author, 'You have already voted to skip this song.')
		await bot.delete_message(ctx.message)

	@commands.command(pass_context=True, no_pm=True)
	async def playing(self, ctx):
		"""Shows info about the currently played song."""

		state = self.get_voice_state(ctx.message.server)
		if state.current is None:
			await self.bot.send_message(ctx.message.author, 'Not playing anything.')
		else:
			skip_count = len(state.skip_votes)
			await self.bot.send_message(ctx.message.author, 'Now playing {} [skips: {}/3]'.format(state.current, skip_count))
		await bot.delete_message(ctx.message)


client = discord.Client()
description = 'r1fT Discord Bot'
bot = commands.Bot(command_prefix='/', description=description)
bot.add_cog(Music(bot))


@bot.event
async def on_ready():
	print('Logged in as')
	print(bot.user.name)
	print(bot.user.id)
	print('------')
	time.sleep(5)
	await bot.change_status(game=discord.Game(name='discord.me/r1ft'), idle=False)
	print('Ready')

@bot.event
async def on_member_join(member):
	nickname = member.display_name
	changednick = nickname.replace(' ', '_')
	await bot.change_nickname(member, changednick)

@bot.event
async def on_member_update(before, after):
	nickname = after.display_name
	changednick = nickname.replace(' ', '_')
	await bot.change_nickname(after, changednick)

#@bot.event
#async def on_voice_state_update(before, after):
#	if state.current is None:
#		await bot.change_status(game=discord.Game(name='discord.me/r1ft'), idle=False)
#	else:
#		musicinfo = 'Now playing {} [skips: {}/3]'.format(state.current, skip_count)
#		await bot.change_status(game=discord.Game(name=musicinfo), idle=False)

@bot.command(pass_context=True)
async def help(ctx, member: discord.Member = None):
	commandmsg = ctx.message
	rolepermission = 0
	if member is None:
		member = ctx.message.author
	with open('help.txt', 'r') as helpfile:
		helpsend=helpfile.read()
	with open('help_admin.txt', 'r') as helpadminfile:
		helpadminsend=helpadminfile.read()
	for r in commandmsg.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 2
	if rolepermission is 0:
		await bot.send_message(commandmsg.author, helpsend)
	if rolepermission is 1:
		await bot.send_message(commandmsg.author, helpsend + helpadminsend)
	if rolepermission is 2:
		await bot.send_message(commandmsg.author, helpsend + helpadminsend)
	devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
	await bot.send_message(devchannel, ctx.message.author.name + ' ```Requested Help```')
	botlog = member.display_name + ' : Requested Help'
	print(botlog)
	await bot.delete_message(commandmsg)


@bot.command(pass_context=True)
async def request(ctx, member: discord.Member = None):
	commandmsg = ctx.message
	temprole = discord.utils.get(commandmsg.server.roles, name="@temp_member")
	if member is None:
		member = ctx.message.author
	await bot.add_roles(commandmsg.author, temprole)
	msg = 'You have been added to @temp_member'
	await bot.send_message(commandmsg.author, msg)
	devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
	await bot.send_message(devchannel, ctx.message.author.name + ' ```Requested Temp Membership```')
	botlog = member.display_name + ' : Requested Temp Membership'
	print(botlog)
	await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def link(ctx, member: discord.Member = None):
	commandmsg = ctx.message
	if member is None:
		member = ctx.message.author
	invitelink = await bot.create_invite(member.server, max_age=60, temporary=True, xkcd=True)
	msg = 'Invite Link : ' + invitelink.url + ' \nThis link is valid for 60 Seconds'
	await bot.send_message(commandmsg.author, msg)
	devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
	await bot.send_message(devchannel, ctx.message.author.name + ' ```Requested Invite Link```')
	botlog = commandmsg.author.display_name + ' : Requested Invite Link'
	print(botlog)
	await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def addmember(ctx, member: discord.Member = None):
	commandmsg = ctx.message
	addedmemberstr = commandmsg.content.replace('/addmember ', '')
	memberrole = discord.utils.get(commandmsg.server.roles, name="@member")
	rolepermission = 0
	if member is None:
		member = ctx.message.author
	for r in commandmsg.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 1
	if rolepermission is 1:
		addedmember = commandmsg.server.get_member_named(addedmemberstr)
		await bot.add_roles(addedmember, memberrole)
		msg = 'You have been added to @member'
		await bot.send_message(addedmember, msg)
		devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
		await bot.send_message(devchannel, ctx.message.author.name + ' ```Added ' + addedmember.display_name + ' to Membership```')
		botlog = commandmsg.author.display_name + ' : Added ' + addedmember.display_name + ' to Membership'
		print(botlog)
		await bot.delete_message(commandmsg)
	else:
		msg = 'You do not have permission to perform this command'
		await bot.send_message(commandmsg.author, msg)
		await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def kick(ctx, member: discord.Member = None):
	commandmsg = ctx.message
	kickedmemberstr = commandmsg.content.replace('/kick ', '')
	rolepermission = 0
	if member is None:
		member = ctx.message.author
	for r in commandmsg.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 1
	for r in commandmsg.server.get_member_named(kickedmemberstr).roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 0
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 0
	if rolepermission is 1:
		kickedmember = commandmsg.server.get_member_named(kickedmemberstr)
		msg = 'You were kicked from the server \n have a nice day'
		await bot.send_message(kickedmember, msg)
		await bot.kick(kickedmember)
		devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
		await bot.send_message(devchannel, ctx.message.author.name + ' ```Kicked ' + kickedmember.display_name + '```')
		botlog = commandmsg.author.display_name + ' : Kicked ' + kickedmember.display_name
		print(botlog)
		await bot.delete_message(commandmsg)
	else:
		msg = 'You do not have permission to perform this command'
		await bot.send_message(commandmsg.author, msg)
		await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def motd(ctx):
	commandmsg = ctx.message
	rolepermission = 0
	msg = commandmsg.content.replace('/motd ', '')
	for r in commandmsg.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 1
	if rolepermission is 1:
		motdchannel = discord.utils.get(commandmsg.server.channels, name="motd")
		await bot.purge_from(motdchannel)
		with open('motd.txt', 'a') as motdfile:
			from time import gmtime, strftime
			motdfile.write(strftime("%Y-%m-%d %H:%M:%S", gmtime()) + " : " + msg + "\n")
			motdfile.close()
		with open('motd.txt', 'r') as motdfile:
			motdsend=motdfile.read()
		with open('motd_End.txt', 'r') as motdendfile:
			motdendsend=motdendfile.read()
		motdpinned = await bot.send_message(motdchannel, "__**Welcome to r1fT_ Discord Channel**__\n" + "\n```" + motdsend + "```\n\n" + motdendsend)
		await bot.pin_message(motdpinned)
		msg = 'Updated #motd'
		await bot.send_message(commandmsg.author, msg)
		devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
		await bot.send_message(devchannel, ctx.message.author.name + ' ```Updated #motd```')
		botlog = commandmsg.author.display_name + ' : Updated #motd'
		print(botlog)
		await bot.delete_message(commandmsg)
	else:
		msg = 'You do not have permission to perform this command'
		await bot.send_message(commandmsg.author, msg)
		await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def motdclear(ctx):
	commandmsg = ctx.message
	rolepermission = 0
	for r in commandmsg.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 1
	if rolepermission is 1:
		motdchannel = discord.utils.get(commandmsg.server.channels, name="motd")
		await bot.purge_from(motdchannel)
		from shutil import copyfile
		copyfile('motd.txt', 'motd.txt.bak')
		with open('motd.txt', 'w') as motdfile:
			motdfile.write("\n")
			motdfile.close()
		with open('motd.txt', 'r') as motdfile:
			motdsend=motdfile.read()
		with open('motd_End.txt', 'r') as motdendfile:
			motdendsend=motdendfile.read()
		motdpinned = await bot.send_message(motdchannel, "__**Welcome to r1fT_ Discord Channel**__\n" + "\n```" + motdsend + "```\n\n" + motdendsend)
		await bot.pin_message(motdpinned)
		msg = 'Updated #motd'
		await bot.send_message(commandmsg.author, msg)
		devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
		await bot.send_message(devchannel, ctx.message.author.name + ' ```Updated #motd```')
		botlog = commandmsg.author.display_name + ' : Updated #motd'
		print(botlog)
		await bot.delete_message(commandmsg)
	else:
		msg = 'You do not have permission to perform this command'
		await bot.send_message(commandmsg.author, msg)
		await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def pin(ctx):
	commandmsg = ctx.message
	rolepermission = 0
	msg = commandmsg.content.replace('/pin ', '')
	for r in ctx.message.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 1
	if rolepermission is 1:
		msgtopin = await bot.send_message(commandmsg.channel, msg)
		await bot.pin_message(msgtopin)
		devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
		await bot.send_message(devchannel, ctx.message.author.name + ' ```Pinned ' + msg + '```')
		botlog = commandmsg.author.display_name + ' : Pinned ' + msg
		print(botlog)
		await bot.delete_message(commandmsg)
	else:
		msg = 'You do not have permission to perform this command'
		await bot.send_message(commandmsg.author, msg)
		await bot.delete_message(commandmsg)

@bot.command(pass_context=True)
async def purge(ctx):
	commandmsg = ctx.message
	rolepermission = 0
	purgeammount = commandmsg.content.replace('/purge ', '')
	purgeammount = int(purgeammount)
	for r in ctx.message.author.roles:
		if r is discord.utils.get(commandmsg.server.roles, name="@admin"):
			rolepermission = 1
		elif r is discord.utils.get(commandmsg.server.roles, name="@owner"):
			rolepermission = 1
	if rolepermission is 1:
		await bot.purge_from(commandmsg.channel, limit=purgeammount)
		purgeammount = str(purgeammount)
		msg = 'You have purged ' + purgeammount + ' messages from #' + commandmsg.channel.name
		await bot.send_message(commandmsg.author, msg)
		devchannel = discord.utils.get(ctx.message.server.channels, name="dev")
		await bot.send_message(devchannel, ctx.message.author.name + ' ```Purged ' + purgeammount + 'messages from #' + commandmsg.channel.name + '```')
		botlog = commandmsg.author.display_name + ' : Purged ' + purgeammount + ' messages from #' + commandmsg.channel.name
		print(botlog)
		await bot.delete_message(commandmsg)
	else:
		msg = 'You do not have permission to perform this command'
		await bot.send_message(commandmsg.author, msg)
		await bot.delete_message(commandmsg)

bot.run('MjE4Mzk2MDEwNzQzOTg4MjI0.CqCqhg.AE4Jzlgq_BCoVCBvnYQlh1C2euI')
