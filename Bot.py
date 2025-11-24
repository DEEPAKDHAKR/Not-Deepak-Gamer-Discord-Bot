import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import random
import asyncio

# Load .env
load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- In-Memory Storage ----------
giveaways = {}
auto_vc_triggers = {}
temp_roles = {}
embeds_store = {}
music_queues = {}

# ---------- Events ----------
@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

# ---------- Basic Commands ----------
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency*1000)}ms")

@bot.command()
async def list(ctx):
    commands_list = """
🎯 Basic Commands
!help
!ping
!list

🎵 Music System
!join
!left
!play
!skip
!pause
!stop

🎉 Giveaway System
!giveaway

👤 Role System
!role_add
!role_remove
!temp_role

📨 DM System
!dm

📝 Embed System
!embedcreate
!embeddelete

📁 Channel System
!channelCreate
!channelDelete

🎧 Auto VC System
!vc_create
!create_vc_remove
"""
    await ctx.send(f"```{commands_list}```")

@bot.command()
async def help(ctx):
    await ctx.send("All commands are listed with !list")

# ---------- Role Commands ----------
@bot.command()
async def role_add(ctx, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await ctx.send(f"Added role {role.name} to {member.mention}")

@bot.command()
async def role_remove(ctx, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await ctx.send(f"Removed role {role.name} from {member.mention}")

@bot.command()
async def temp_role(ctx, member: discord.Member, role: discord.Role, time: str):
    await member.add_roles(role)
    await ctx.send(f"Temporary role {role.name} added to {member.mention} for {time}")
    seconds = int(time[:-1]) * (60 if time.endswith("m") else 1)
    task = asyncio.create_task(remove_temp_role(member, role, seconds))
    temp_roles[f"{member.id}:{role.id}"] = task

async def remove_temp_role(member, role, seconds):
    await asyncio.sleep(seconds)
    await member.remove_roles(role)

# ---------- DM Command ----------
@bot.command()
async def dm(ctx, member: discord.Member, *, message):
    try:
        await member.send(message)
        await ctx.send(f"Sent DM to {member.mention}")
    except:
        await ctx.send(f"Could not DM {member.mention}")

# ---------- Embed Commands ----------
@bot.command()
async def embedcreate(ctx, trigger_name, title, *, message):
    embeds_store[trigger_name] = {"title": title, "message": message}
    await ctx.send(f"Embed saved with trigger: {trigger_name}")

@bot.command()
async def embeddelete(ctx, trigger_name):
    if trigger_name in embeds_store:
        del embeds_store[trigger_name]
        await ctx.send(f"Embed {trigger_name} deleted.")
    else:
        await ctx.send(f"Embed {trigger_name} not found.")

# ---------- Channel Commands ----------
@bot.command()
async def channelCreate(ctx, name, type_channel, category=None, private="No"):
    type_channel = type_channel.lower()
    if type_channel == "voice":
        ctype = discord.ChannelType.voice
    else:
        ctype = discord.ChannelType.text
    overwrites = None
    if private.lower() == "yes":
        overwrites = {ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    cat = None
    if category:
        cat = discord.utils.get(ctx.guild.categories, name=category)
    ch = await ctx.guild.create_text_channel(name, category=cat, overwrites=overwrites) if ctype==discord.ChannelType.text else await ctx.guild.create_voice_channel(name, category=cat, overwrites=overwrites)
    await ctx.send(f"Created {ch.name} ({ctype.name})")

@bot.command()
async def channelDelete(ctx, name, type_channel):
    type_channel = type_channel.lower()
    if type_channel == "voice":
        ctype = discord.ChannelType.voice
    else:
        ctype = discord.ChannelType.text
    ch = discord.utils.get(ctx.guild.channels, name=name, type=ctype)
    if ch:
        await ch.delete()
        await ctx.send(f"Deleted {name}")
    else:
        await ctx.send(f"Channel not found.")

# ---------- Giveaway Command ----------
@bot.command()
async def giveaway(ctx, duration: str, winners: int, *, prize):
    seconds = int(duration[:-1]) * (60 if duration.endswith("m") else 1)
    msg = await ctx.send(f"🎉 **GIVEAWAY** 🎉\nPrize: {prize}\nWinners: {winners}\nReact with 🎉 to enter!")
    await msg.add_reaction("🎉")
    giveaways[msg.id] = {"winners": winners, "prize": prize, "message": msg}
    await asyncio.sleep(seconds)
    msg = giveaways[msg.id]["message"]
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    users = await reaction.users().flatten() if reaction else []
    entrants = [u for u in users if not u.bot]
    if entrants:
        winners_list = random.sample(entrants, min(winners, len(entrants)))
        mentions = ", ".join([w.mention for w in winners_list])
        await ctx.send(f"Giveaway ended! Winners: {mentions} — Prize: {prize}")
    else:
        await ctx.send("No valid entries.")
    del giveaways[msg.id]

# ---------- Auto VC System ----------
@bot.command()
async def vc_create(ctx, trigger_channel: discord.VoiceChannel, delete_time: str):
    seconds = int(delete_time[:-1]) * (60 if delete_time.endswith("m") else 1)
    auto_vc_triggers[trigger_channel.id] = {"delete_time": seconds}
    await ctx.send(f"Auto VC trigger set for {trigger_channel.name} with delete time {delete_time}")

@bot.command()
async def create_vc_remove(ctx, trigger_channel_name):
    channel = discord.utils.get(ctx.guild.channels, name=trigger_channel_name)
    if channel and channel.id in auto_vc_triggers:
        del auto_vc_triggers[channel.id]
        await ctx.send(f"Removed {trigger_channel_name} from auto VC triggers")
    else:
        await ctx.send(f"Trigger channel not found.")

@bot.event
async def on_voice_state_update(member, before, after):
    # User joined trigger channel
    if after.channel and after.channel.id in auto_vc_triggers:
        name = f"{member.name}'s VC"
        ch = await member.guild.create_voice_channel(name)
        await member.move_to(ch)
        ch._auto_vc_delete_time = auto_vc_triggers[after.channel.id]["delete_time"]
    # Check if auto VC empty
    if before.channel and hasattr(before.channel, "_auto_vc_delete_time"):
        if len(before.channel.members) == 0:
            await asyncio.sleep(before.channel._auto_vc_delete_time)
            if len(before.channel.members) == 0:
                await before.channel.delete()

# ---------- Music System Placeholder ----------
# You can add YouTube / Spotify music system using discord.py voice here

# ---------- Run Bot ----------
bot.run(TOKEN)        q.player.stop();
        return interaction.reply({ content: 'Skipped.', ephemeral: true });
      }
      if (id === 'pause') {
        q.player.pause();
        return interaction.reply({ content: 'Paused.', ephemeral: true });
      }
      if (id === 'stop') {
        q.player.stop(true);
        q.queue = [];
        const conn = getVoiceConnection(guildId);
        if (conn) conn.destroy();
        musicQueues.delete(guildId);
        return interaction.reply({ content: 'Stopped and cleared queue.', ephemeral: true });
      }
      return;
    }

    if (!interaction.isChatInputCommand()) return;

    switch (interaction.commandName) {
      case 'ping':
        await interaction.reply(`Pong! ${Date.now() - interaction.createdTimestamp}ms`);
        break;

      case 'help':
      case 'list': {
        const embed = new EmbedBuilder()
          .setTitle('Command List')
          .setDescription('All commands supported by the bot')
          .addFields(
            { name: 'Basic', value: '/help, /ping, /list' },
            { name: 'Music', value: '/join, /left, /play, /skip, /pause, /stop' },
            { name: 'Giveaway', value: '/giveaway' },
            { name: 'Roles', value: '/role_add, /role_remove, /temp_role' },
            { name: 'DM', value: '/dm' },
            { name: 'Embed', value: '/embedcreate, /embeddelete' },
            { name: 'Channels', value: '/channelcreate, /channeldelete' },
            { name: 'Auto VC', value: '/vc_create, /create_vc_remove' },
          );
        await interaction.reply({ embeds: [embed] });
        break;
      }

      // ------- Music -------
      case 'join': {
        const member = interaction.member;
        const voiceChannel = member.voice.channel;
        if (!voiceChannel) return interaction.reply({ content: 'You must be in a voice channel.', ephemeral: true });
        const guildId = interaction.guildId;
        const q = ensureMusic(guildId);
        const connection = joinVoiceChannel({
          channelId: voiceChannel.id,
          guildId,
          adapterCreator: interaction.guild.voiceAdapterCreator,
        });
        q.connection = connection;
        q.player.on('error', e => console.error('Player error', e));
        connection.subscribe(q.player);
        await interaction.reply({ content: `Joined ${voiceChannel.name}` });
        break;
      }

      case 'left': {
        const conn = getVoiceConnection(interaction.guildId);
        if (conn) {
          conn.destroy();
          musicQueues.delete(interaction.guildId);
          await interaction.reply('Left the voice channel.');
        } else {
          await interaction.reply({ content: 'Not connected.', ephemeral: true });
        }
        break;
      }

      case 'play': {
        const query = interaction.options.getString('query', true);
        const voiceChannel = interaction.member.voice.channel;
        if (!voiceChannel) return interaction.reply({ content: 'Join a voice channel first.', ephemeral: true });
        // For simplicity, accept direct YouTube links; if not link, try as URL (ytdl can accept many)
        let url = query;
        // If not URL, try as direct (user must provide URL ideally).
        // Get title
        let info;
        try {
          if (!ytdl.validateURL(url)) {
            // not a valid URL, reply asking for a YouTube URL
            return interaction.reply({ content: 'Please provide a valid YouTube URL for now.', ephemeral: true });
          }
          info = await ytdl.getBasicInfo(url);
        } catch (e) {
          return interaction.reply({ content: 'Failed to get stream info. Provide a valid YouTube link.', ephemeral: true });
        }

        const guildId = interaction.guildId;
        const q = ensureMusic(guildId);
        q.textChannel = interaction.channel;
        q.queue.push({ url, title: info.videoDetails.title, requestedBy: `<@${interaction.user.id}>` });

        // If not playing, join and start
        if (!q.connection) {
          const connection = joinVoiceChannel({
            channelId: voiceChannel.id,
            guildId,
            adapterCreator: interaction.guild.voiceAdapterCreator,
          });
          q.connection = connection;
          connection.subscribe(q.player);
        }
        // If player is idle, start
        if (q.player.state.status !== AudioPlayerStatus.Playing) {
          await interaction.reply({ content: `Queued: **${info.videoDetails.title}**`, components: [musicControlRow()] });
          playNext(guildId);
        } else {
          await interaction.reply({ content: `Queued: **${info.videoDetails.title}**`, components: [musicControlRow()] });
        }
        break;
      }

      case 'skip': {
        const q = musicQueues.get(interaction.guildId);
        if (!q) return interaction.reply({ content: 'Nothing to skip.', ephemeral: true });
        q.player.stop();
        await interaction.reply('Skipped.');
        break;
      }

      case 'pause': {
        const q = musicQueues.get(interaction.guildId);
        if (!q) return interaction.reply({ content: 'No active player.', ephemeral: true });
        q.player.pause();
        await interaction.reply('Paused.');
        break;
      }

      case 'stop': {
        const q = musicQueues.get(interaction.guildId);
        if (!q) return interaction.reply({ content: 'No active player.', ephemeral: true });
        q.player.stop(true);
        q.queue = [];
        const conn = getVoiceConnection(interaction.guildId);
        if (conn) conn.destroy();
        musicQueues.delete(interaction.guildId);
        await interaction.reply('Stopped and cleared queue.');
        break;
      }

      // ------- Giveaway -------
      case 'giveaway': {
        const durationStr = interaction.options.getString('duration', true);
        const winners = interaction.options.getInteger('winners', true);
        const prize = interaction.options.getString('prize', true);
        const durationMs = ms(durationStr);
        if (!durationMs || durationMs <= 0) return interaction.reply({ content: 'Invalid duration.', ephemeral: true });

        const embed = new EmbedBuilder().setTitle('Giveaway').setDescription(`Prize: **${prize}**\nWinners: ${winners}\nEnds in: ${durationStr}`).setTimestamp();
        const msg = await interaction.reply({ embeds: [embed], fetchReply: true });

        // Reaction-based entry
        await msg.react('🎉');
        const gId = msg.id;
        giveaways.set(gId, { message: msg, endAt: Date.now() + durationMs, winners, prize });

        setTimeout(async () => {
          const g = giveaways.get(gId);
          if (!g) return;
          const fetched = await g.message.fetch();
          const reaction = fetched.reactions.cache.get('🎉');
          const users = reaction ? await reaction.users.fetch() : new Map();
          const entrants = users.filter(u => !u.bot).map(u => u);
          if (entrants.length === 0) {
            g.message.reply('No valid entries. Giveaway canceled.');
            giveaways.delete(gId);
            return;
          }
          // pick winners
          const picked = [];
          const entrantsArr = Array.from(entrants.values());
          for (let i=0; i<Math.min(g.winners, entrantsArr.length); i++) {
            const idx = Math.floor(Math.random() * entrantsArr.length);
            picked.push(entrantsArr.splice(idx, 1)[0]);
          }
          const mention = picked.map(u => `<@${u.id}>`).join(', ');
          g.message.channel.send({ content: `Giveaway ended! Winners: ${mention} — Prize: **${g.prize}**` });
          giveaways.delete(gId);
        }, durationMs);

        break;
      }

      // ------- Role add/remove/temp -------
      case 'role_add': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageRoles)) return interaction.reply({ content: 'You need Manage Roles permission.', ephemeral: true });
        const role = interaction.options.getRole('role', true);
        const member = interaction.options.getMember('member', true);
        await member.roles.add(role).catch(e => console.error(e));
        await interaction.reply({ content: `Added role ${role.name} to ${member.user.tag}` });
        break;
      }

      case 'role_remove': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageRoles)) return interaction.reply({ content: 'You need Manage Roles permission.', ephemeral: true });
        const role = interaction.options.getRole('role', true);
        const member = interaction.options.getMember('member', true);
        await member.roles.remove(role).catch(e => console.error(e));
        await interaction.reply({ content: `Removed role ${role.name} from ${member.user.tag}` });
        break;
      }

      case 'temp_role': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageRoles)) return interaction.reply({ content: 'You need Manage Roles permission.', ephemeral: true });
        const role = interaction.options.getRole('role', true);
        const member = interaction.options.getMember('member', true);
        const durationStr = interaction.options.getString('time', true);
        const durationMs = ms(durationStr);
        if (!durationMs || durationMs <= 0) return interaction.reply({ content: 'Invalid time.', ephemeral: true });
        await member.roles.add(role).catch(e => console.error(e));
        await interaction.reply({ content: `Temporary role ${role.name} added to ${member.user.tag} for ${durationStr}` });

        // schedule remove
        const timeout = setTimeout(async () => {
          try {
            await member.roles.remove(role);
          } catch (e) { /* ignored */ }
          tempRoles.delete(member.id + ':' + role.id);
        }, durationMs);
        tempRoles.set(member.id + ':' + role.id, timeout);
        break;
      }

      // ------- DM -------
      case 'dm': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageGuild)) return interaction.reply({ content: 'You need Manage Server permission to DM.', ephemeral: true });
        const user = interaction.options.getUser('user', true);
        const message = interaction.options.getString('message', true);
        try {
          await user.send(message);
          await interaction.reply({ content: `Sent DM to ${user.tag}` });
        } catch (e) {
          await interaction.reply({ content: `Failed to DM ${user.tag}`, ephemeral: true });
        }
        break;
      }

      // ------- Embed create/delete -------
      case 'embedcreate': {
        const trigger = interaction.options.getString('trigger', true);
        const title = interaction.options.getString('title', true);
        const message = interaction.options.getString('message', true);

        // For demo: store in memory on client
        client.embeds = client.embeds || {};
        client.embeds[trigger] = { title, message, author: interaction.user.tag };
        await interaction.reply({ content: `Embed saved with trigger name: ${trigger}` });
        break;
      }

      case 'embeddelete': {
        const name = interaction.options.getString('name', true);
        client.embeds = client.embeds || {};
        if (client.embeds[name]) {
          delete client.embeds[name];
          await interaction.reply({ content: `Embed '${name}' deleted.` });
        } else {
          await interaction.reply({ content: `Embed '${name}' not found.`, ephemeral: true });
        }
        break;
      }

      // ------- Channel create/delete -------
      case 'channelcreate': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageChannels)) return interaction.reply({ content: 'You need Manage Channels permission.', ephemeral: true });
        const name = interaction.options.getString('name', true);
        const type = interaction.options.getString('type', true).toLowerCase();
        const categoryName = interaction.options.getString('category', false);
        const isPrivate = (interaction.options.getString('private') || 'No').toLowerCase() === 'yes';

        const guild = interaction.guild;
        // find category
        let parent = null;
        if (categoryName) {
          parent = guild.channels.cache.find(c => c.type === 4 && c.name === categoryName);
        }
        const created = await guild.channels.create({
          name,
          type: type === 'voice' ? 2 : 0,
          parent: parent ? parent.id : null,
          permissionOverwrites: isPrivate ? [{ id: guild.roles.everyone.id, deny: [PermissionsBitField.Flags.ViewChannel] }] : undefined,
        });
        await interaction.reply({ content: `Channel created: ${created.name}` });
        break;
      }

      case 'channeldelete': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageChannels)) return interaction.reply({ content: 'You need Manage Channels permission.', ephemeral: true });
        const name = interaction.options.getString('name', true);
        const type = interaction.options.getString('type', true).toLowerCase();
        const chan = interaction.guild.channels.cache.find(c => c.name === name && ((type === 'voice' && c.type === 2) || (type === 'text' && c.type === 0)));
        if (!chan) return interaction.reply({ content: 'Channel not found.', ephemeral: true });
        await chan.delete();
        await interaction.reply({ content: `Deleted channel ${name}` });
        break;
      }

      // ------- Auto VC -------
      case 'vc_create': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageChannels)) return interaction.reply({ content: 'You need Manage Channels permission.', ephemeral: true });
        const channel = interaction.options.getChannel('channel', true);
        const deleteTimeStr = interaction.options.getString('delete_time', true);
        const deleteMs = ms(deleteTimeStr);
        if (!deleteMs) return interaction.reply({ content: 'Invalid delete time.', ephemeral: true });
        // store trigger
        autoVCTriggers.set(channel.id, { deleteTimeMs: deleteMs, categoryId: channel.parentId || null });
        await interaction.reply({ content: `Auto VC trigger set for channel ${channel.name}. Delete time: ${deleteTimeStr}` });
        break;
      }

      case 'create_vc_remove': {
        if (!interaction.member.permissions.has(PermissionsBitField.Flags.ManageChannels)) return interaction.reply({ content: 'You need Manage Channels permission.', ephemeral: true });
        const name = interaction.options.getString('channel_name', true);
        const chan = interaction.guild.channels.cache.find(c => c.name === name && autoVCTriggers.has(c.id));
        if (!chan) return interaction.reply({ content: 'Trigger channel not found in auto VC system.', ephemeral: true });
        autoVCTriggers.delete(chan.id);
        await interaction.reply({ content: `Removed ${name} from auto VC triggers.` });
        break;
      }

      default:
        await interaction.reply({ content: 'Not implemented', ephemeral: true });
        break;
    }
  } catch (err) {
    console.error('Interaction error', err);
    if (interaction.replied || interaction.deferred) {
      interaction.followUp({ content: 'There was an error while executing this command.', ephemeral: true }).catch(() => {});
    } else {
      interaction.reply({ content: 'There was an error while executing this command.', ephemeral: true }).catch(() => {});
    }
  }
});

// ---------- Auto VC: Listen to voiceStateUpdate to create/delete voice channels ----------
client.on('voiceStateUpdate', async (oldState, newState) => {
  try {
    // User joined the trigger channel?
    if (!oldState.channel && newState.channel) {
      // joined a channel
      const trigger = autoVCTriggers.get(newState.channel.id);
      if (trigger) {
        // create a new voice channel with user name
        const guild = newState.guild;
        const channelName = `${newState.member.user.username}'s VC`;
        const created = await guild.channels.create({
          name: channelName,
          type: 2, // voice
          parent: trigger.categoryId,
          permissionOverwrites: [
            {
              id: guild.roles.everyone.id,
              allow: [PermissionsBitField.Flags.ViewChannel, PermissionsBitField.Flags.Connect],
            }
          ]
        });

        // Move the user to the newly created channel
        await newState.member.voice.setChannel(created.id);
        // store meta on channel for deletion scheduling
        created._autoVC = {
          deleteAfterMs: trigger.deleteTimeMs
        };
      }
    }

    // User left a channel -> if the channel was created by the system and empty -> delete after timer
    if (oldState.channel && !newState.channel) {
      const ch = oldState.channel;
      if (ch._autoVC) {
        // schedule deletion after configured time if still empty
        setTimeout(async () => {
          const fetched = await ch.guild.channels.fetch(ch.id).catch(() => null);
          if (!fetched) return;
          const members = fetched.members.size;
          if (members === 0) {
            try {
              await fetched.delete(`Auto VC deleted after ${ch._autoVC.deleteAfterMs}ms`);
            } catch (e) { /* ignore */ }
          }
        }, ch._autoVC.deleteAfterMs);
      }
    }
  } catch (e) {
    console.error('voiceStateUpdate error', e);
  }
});

// ---------- Login ----------
client.login(config.TOKEN);
