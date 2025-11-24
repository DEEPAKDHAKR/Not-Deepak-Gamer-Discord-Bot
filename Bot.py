
/**
 * Full Discord.js v14 bot (single file)
 * - Commands: music, roles, giveaways, embed, channels, auto VC
 * - Not production hardened (use DB and error handling for production)
 *
 * npm: discord.js@14 @discordjs/voice ytdl-core ms
 */

const { Client, GatewayIntentBits, Partials, Collection, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, PermissionsBitField, Routes, REST, SlashCommandBuilder } = require('discord.js');
const { joinVoiceChannel, createAudioPlayer, createAudioResource, AudioPlayerStatus, NoSubscriberBehavior, getVoiceConnection } = require('@discordjs/voice');
const ytdl = require('ytdl-core');
const ms = require('ms');

// ---------- CONFIG ----------
const config = {
  TOKEN: 'MTE4MDQ1ODA2NzQwMjQzNjYxOA.GI5V-L.TjPhSH7eTCksB0LX4yS9RqHV1-HjGJWjoxDC7E',
  CLIENT_ID: '1180458067402436618',       // bot application id
  GUILD_ID: 'YOUR_TEST_GUILD_ID_HERE',    // for quick guild command register (dev)
  PREFIX: '/',
};
// -----------------------------

// In-memory stores (replace with DB for real use)
const giveaways = new Collection(); // giveawayId -> giveaway data
const tempRoles = new Collection(); // userId -> timeout
const autoVCTriggers = new Collection(); // channelId -> { deleteTimeMs, categoryId, private, memberLimit }

// Music queues per guild
const musicQueues = new Collection(); // guildId -> { connection, player, queue: [{url, title, requestedBy}], textChannel }

// Create client
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent
  ],
  partials: [Partials.Channel]
});

// ---------- REGISTER SLASH COMMANDS (guild-scoped for quick dev) ----------
const commands = [
  new SlashCommandBuilder().setName('ping').setDescription('Ping the bot.'),
  new SlashCommandBuilder().setName('list').setDescription('List all commands.'),
  new SlashCommandBuilder().setName('help').setDescription('Show help.'),

  // Music
  new SlashCommandBuilder().setName('join').setDescription('Join your VC.'),
  new SlashCommandBuilder().setName('left').setDescription('Leave the voice channel.'),
  new SlashCommandBuilder().setName('play').setDescription('Play a YouTube URL or search term.').addStringOption(opt => opt.setName('query').setDescription('YouTube URL or search').setRequired(true)),
  new SlashCommandBuilder().setName('skip').setDescription('Skip current song.'),
  new SlashCommandBuilder().setName('pause').setDescription('Pause playback.'),
  new SlashCommandBuilder().setName('stop').setDescription('Stop and clear queue.'),

  // Giveaway
  new SlashCommandBuilder().setName('giveaway').setDescription('Start a giveaway').addStringOption(o => o.setName('duration').setDescription('e.g. 1m, 1h').setRequired(true)).addIntegerOption(o => o.setName('winners').setDescription('Number of winners').setRequired(true)).addStringOption(o => o.setName('prize').setDescription('Prize').setRequired(true)),

  // Roles
  new SlashCommandBuilder().setName('role_add').setDescription('Add role to user').addRoleOption(o => o.setName('role').setDescription('Role to add').setRequired(true)).addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)),
  new SlashCommandBuilder().setName('role_remove').setDescription('Remove role from user').addRoleOption(o => o.setName('role').setDescription('Role to remove').setRequired(true)).addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)),
  new SlashCommandBuilder().setName('temp_role').setDescription('Add temporary role').addRoleOption(o => o.setName('role').setDescription('Role').setRequired(true)).addUserOption(o => o.setName('member').setDescription('Member').setRequired(true)).addStringOption(o => o.setName('time').setDescription('Duration (e.g. 10m)').setRequired(true)),

  // DM
  new SlashCommandBuilder().setName('dm').setDescription('Send DM to user').addUserOption(o => o.setName('user').setDescription('User').setRequired(true)).addStringOption(o => o.setName('message').setDescription('Message').setRequired(true)),

  // Embed
  new SlashCommandBuilder().setName('embedcreate').setDescription('Create embed message').addStringOption(o => o.setName('trigger').setDescription('trigger name').setRequired(true)).addStringOption(o => o.setName('title').setDescription('Embed title').setRequired(true)).addStringOption(o => o.setName('message').setDescription('Embed message').setRequired(true)),
  new SlashCommandBuilder().setName('embeddelete').setDescription('Delete embed (by trigger name)').addStringOption(o => o.setName('name').setDescription('Embed trigger name').setRequired(true)),

  // Channel
  new SlashCommandBuilder().setName('channelcreate').setDescription('Create a channel').addStringOption(o => o.setName('name').setDescription('Name').setRequired(true)).addStringOption(o => o.setName('type').setDescription('text or voice').setRequired(true)).addStringOption(o => o.setName('category').setDescription('Category name').setRequired(false)).addStringOption(o => o.setName('private').setDescription('Yes or No').setRequired(false)),
  new SlashCommandBuilder().setName('channeldelete').setDescription('Delete a channel').addStringOption(o => o.setName('name').setDescription('Channel name').setRequired(true)).addStringOption(o => o.setName('type').setDescription('text or voice').setRequired(true)),

  // Auto VC
  new SlashCommandBuilder().setName('vc_create').setDescription('Register an auto-create VC trigger channel').addChannelOption(o => o.setName('channel').setDescription('Trigger channel (select)').setRequired(true)).addStringOption(o => o.setName('delete_time').setDescription('Delete time after leave (e.g. 30s, 1m)').setRequired(true)),
  new SlashCommandBuilder().setName('create_vc_remove').setDescription('Remove channel from auto VC system').addStringOption(o => o.setName('channel_name').setDescription('Trigger channel name').setRequired(true)),
];

(async () => {
  const rest = new REST({ version: '10' }).setToken(config.TOKEN);
  try {
    console.log('Registering slash commands to guild...');
    await rest.put(Routes.applicationGuildCommands(config.CLIENT_ID, config.GUILD_ID), { body: commands.map(c => c.toJSON()) });
    console.log('Commands registered.');
  } catch (err) {
    console.error('Failed to register commands', err);
  }
})();

// ---------- Helpers ----------
function ensureMusic(guildId) {
  if (!musicQueues.has(guildId)) {
    musicQueues.set(guildId, { connection: null, player: createAudioPlayer({ behaviors: { noSubscriber: NoSubscriberBehavior.Play } }), queue: [], textChannel: null });
  }
  return musicQueues.get(guildId);
}

async function playNext(guildId) {
  const q = musicQueues.get(guildId);
  if (!q) return;
  if (q.queue.length === 0) {
    // stop and destroy connection after a timeout
    const conn = getVoiceConnection(guildId);
    if (conn) conn.destroy();
    musicQueues.delete(guildId);
    return;
  }
  const track = q.queue.shift();
  const stream = ytdl(track.url, { filter: 'audioonly', highWaterMark: 1<<25 });
  const resource = createAudioResource(stream);
  q.player.play(resource);
  q.textChannel?.send({ embeds: [new EmbedBuilder().setTitle('Now Playing').setDescription(`${track.title}\nRequested by: ${track.requestedBy}`).setTimestamp()] });

  q.player.once(AudioPlayerStatus.Idle, () => playNext(guildId));
}

// ---------- Buttons for music
function musicControlRow() {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('skip').setLabel('Skip').setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId('pause').setLabel('Pause').setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId('stop').setLabel('Stop').setStyle(ButtonStyle.Danger),
  );
}

// ---------- Event: ready
client.once('ready', () => {
  console.log(`Logged in as ${client.user.tag}`);
});

// ---------- Interaction Create (slash commands + buttons)
client.on('interactionCreate', async (interaction) => {
  try {
    if (interaction.isButton()) {
      // Music control buttons
      const id = interaction.customId;
      const guildId = interaction.guildId;
      const q = ensureMusic(guildId);
      if (!q) return interaction.reply({ content: 'No music session.', ephemeral: true });
      if (id === 'skip') {
        q.player.stop();
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
