import json
import os
import re
from typing import Callable, Any, Optional, Union

from mcdreforged.api.all import *

from location_marker import constants
from location_marker.storage import LocationStorage, Point, Location


class Config(Serializable):
	teleport_hint_on_coordinate: bool = True
	item_per_page: int = 10


config: Config
storage = LocationStorage()
server_inst: PluginServerInterface


def show_help(source: CommandSource):
	help_msg_lines = '''
--------- MCDR 路标插件 v{2} ---------
一个位于服务端的路标管理插件
§7{0}§r 显示此帮助信息
§7{0} list §6[<可选页号>]§r 列出所有路标
§7{0} search §3<关键字> §6[<可选页号>]§r 搜索坐标，返回所有匹配项
§7{0} add §b<路标名称> §e<x> <y> <z> <维度id> §6[<可选注释>]§r 加入一个路标
§7{0} add §b<路标名称> §ehere §6[<可选注释>]§r 加入自己所处位置、维度的路标
§7{0} del §b<路标名称>§r 删除路标，要求全字匹配
§7{0} info §b<路标名称>§r 显示路标的详情等信息
§7{0} §3<关键字> §6[<可选页号>]§r 同 §7{0} search§r
其中：
当§6可选页号§r被指定时，将以每{1}个路标为一页，列出指定页号的路标
§3关键字§r以及§b路标名称§r为不包含空格的一个字符串，或者一个被""括起的字符串
'''.format(constants.PREFIX, config.item_per_page, server_inst.get_self_metadata().version).splitlines(True)
	help_msg_rtext = RTextList()
	for line in help_msg_lines:
		result = re.search(r'(?<=§7)!!loc[\w ]*(?=§)', line)
		if result is not None:
			help_msg_rtext.append(RText(line).c(RAction.suggest_command, result.group()).h('点击以填入 §7{}§r'.format(result.group())))
		else:
			help_msg_rtext.append(line)
	source.reply(help_msg_rtext)


def get_coordinate_text(coord: Point, dimension: int, *, color=RColor.green, precision: int = 1):
	def tp_hint(text):
		if config.teleport_hint_on_coordinate:
			text.c(RAction.suggest_command, '/execute in {} run tp {} {} {}'.format(get_dim_key(dimension), coord.x, coord.y, coord.z)).h('点击以传送')
		return text

	def ltr(text):
		return tp_hint(RText(text, color=color))

	def ele(value):
		return tp_hint(RText(str(round(value, precision)), color=color)).h(value)

	return RTextList(ltr('['), ele(coord.x), ltr(', '), ele(coord.y), ltr(', '), ele(coord.z), ltr(']'))


def get_dim_key(dim: Union[int, str]) -> str:
	dimension_convert = {0: 'minecraft:overworld', -1: 'minecraft:the_nether', 1: 'minecraft:the_end'}
	return dimension_convert.get(dim, dim)


def get_dimension_text(dim: Union[int, str]) -> RTextBase:
	dim_key = get_dim_key(dim)
	dimension_color = {
		'minecraft:overworld': RColor.dark_green,
		'minecraft:the_nether': RColor.dark_red,
		'minecraft:the_end': RColor.dark_purple
	}
	dimension_translation = {
		'minecraft:overworld': 'createWorld.customize.preset.overworld',
		'minecraft:the_nether': 'advancements.nether.root.title',
		'minecraft:the_end': 'advancements.end.root.title'
	}
	if dim_key in dimension_color:
		return RTextTranslation(dimension_translation[dim_key], color=dimension_color[dim_key]).h(dim_key)
	else:
		return RText(dim_key, color=RColor.gray).h(dim_key)


def print_location(location: Location, printer: Callable[[RTextBase], Any], *, show_list_symbol: bool):
	name_text = RText(location.name)
	if location.desc is not None:
		name_text.h(location.desc)
	text = RTextList(
		name_text.h('点击以显示详情').c(RAction.run_command, '{} info {}'.format(constants.PREFIX, location.name)),
		' ',
		get_coordinate_text(location.pos, location.dim),
		' §7@§r ',
		get_dimension_text(location.dim)
	)
	if show_list_symbol:
		text = RText('- ', color=RColor.gray) + text
	printer(text)


def reply_location_as_item(source: CommandSource, location: Location):
	print_location(location, lambda msg: source.reply(msg), show_list_symbol=True)


def broadcast_location(server: ServerInterface, location: Location):
	print_location(location, lambda msg: server.say(msg), show_list_symbol=False)


def list_locations(source: CommandSource, *, keyword: Optional[str] = None, page: Optional[int] = None):
	matched_locations = []
	for loc in storage.get_locations():
		if keyword is None or loc.name.find(keyword) != -1 or (loc.desc is not None and loc.desc.find(keyword) != -1):
			matched_locations.append(loc)
	matched_count = len(matched_locations)
	if page is None:
		for loc in matched_locations:
			reply_location_as_item(source, loc)
	else:
		command_base = constants.PREFIX
		if keyword is None:
			command_base += ' list'
		else:
			command_base += ' search {}'.format(json.dumps(keyword, ensure_ascii=False))
		left, right = (page - 1) * config.item_per_page, page * config.item_per_page
		for i in range(left, right):
			if 0 <= i < matched_count:
				reply_location_as_item(source, matched_locations[i])

		has_prev = 0 < left < matched_count
		has_next = 0 < right < matched_count
		color = {False: RColor.dark_gray, True: RColor.gray}
		prev_page = RText('<-', color=color[has_prev])
		if has_prev:
			prev_page.c(RAction.run_command, '{} {}'.format(command_base, page - 1)).h('点击显示上一页')
		next_page = RText('->', color=color[has_next])
		if has_next:
			next_page.c(RAction.run_command, '{} {}'.format(command_base, page + 1)).h('点击显示下一页')

		source.reply(RTextList(
			prev_page,
			' 第§6{}§r页 '.format(page),
			next_page
		))
	if keyword is None:
		source.reply('共有§6{}§r个路标'.format(matched_count))
	else:
		source.reply('共找到§6{}§r个路标'.format(matched_count))


def add_location(source: CommandSource, name, x, y, z, dim, desc=None):
	if storage.contains(name):
		source.reply('路标§b{}§r已存在，无法添加'.format(name))
		return
	try:
		location = Location(name=name, desc=desc, dim=dim, pos=Point(x=x, y=y, z=z))
		storage.add(location)
	except Exception as e:
		source.reply('路标§b{}§r添加§c失败§r: {}'.format(name, e))
		server_inst.logger.exception('Failed to add location {}'.format(name))
	else:
		source.get_server().say('路标§b{}§r添加§a成功'.format(name))
		broadcast_location(source.get_server(), location)


@new_thread('LocationMarker')
def add_location_here(source: CommandSource, name, desc=None):
	if not isinstance(source, PlayerCommandSource):
		source.reply('仅有玩家允许使用本指令')
		return
	api = source.get_server().get_plugin_instance('minecraft_data_api')
	pos = api.get_player_coordinate(source.player)
	dim = api.get_player_dimension(source.player)
	add_location(source, name, pos.x, pos.y, pos.z, dim, desc)


def delete_location(source: CommandSource, name):
	loc = storage.remove(name)
	if loc is not None:
		source.get_server().say('已删除路标§b{}§r'.format(name))
		broadcast_location(source.get_server(), loc)
	else:
		source.reply('未找到路标§b{}§r'.format(name))


def show_location_detail(source: CommandSource, name):
	loc = storage.get(name)
	if loc is not None:
		broadcast_location(source.get_server(), loc)
		source.reply(RTextList('路标名: ', RText(loc.name, color=RColor.aqua)))
		source.reply(RTextList('坐标: ', get_coordinate_text(loc.pos, loc.dim, precision=4)))
		source.reply(RTextList('详情: ', RText(loc.desc if loc.desc is not None else '无', color=RColor.gray)))
		x, y, z = map(round, loc.pos)
		source.reply('VoxelMap路标: [name:{}, x:{}, y:{}, z:{}, dim:{}]'.format(loc.name, x, y, z, loc.dim))
		source.reply('VoxelMap路标(1.16+): [name:{}, x:{}, y:{}, z:{}, dim:{}]'.format(loc.name, x, y, z, get_dim_key(loc.dim)))
		# <Location Marker> xaero-waypoint:test:T:9987:71:9923:6:false:0:Internal-overworld-waypoints
		source.reply('<{}> xaero-waypoint:{}:{}:{}:{}:{}:6:false:0:Internal-{}-waypoints'.format(server_inst.get_self_metadata().name, loc.name, loc.name[0], x, y, z, get_dim_key(loc.dim).replace('minecraft:', '')))
	else:
		source.reply('未找到路标§b{}§r'.format(name))


def on_load(server: PluginServerInterface, old_inst):
	global config, storage, server_inst
	server_inst = server
	config = server.load_config_simple(constants.CONFIG_FILE, target_class=Config)
	storage.load(os.path.join(server.get_data_folder(), constants.STORAGE_FILE))

	server.register_help_message(constants.PREFIX, '路标管理')
	search_node = QuotableText('keyword').\
		runs(lambda src, ctx: list_locations(src, keyword=ctx['keyword'])).\
		then(Integer('page').runs(lambda src, ctx: list_locations(src, keyword=ctx['keyword'], page=ctx['page'])))

	server.register_command(
		Literal(constants.PREFIX).
		runs(show_help).
		then(Literal('all').runs(lambda src: list_locations(src))).
		then(
			Literal('list').runs(lambda src: list_locations(src)).
			then(Integer('page').runs(lambda src, ctx: list_locations(src, page=ctx['page'])))
		).
		then(Literal('search').then(search_node)).
		then(search_node).  # for lazyman
		then(
			Literal('add').then(
				QuotableText('name').
				then(
					Literal('here').runs(lambda src, ctx: add_location_here(src, ctx['name'])).
					then(GreedyText('desc').runs(lambda src, ctx: add_location_here(src, ctx['name'], ctx['desc'])))
				).
				then(
					Number('x').then(Number('y').then(Number('z').then(
						Integer('dim').in_range(-1, 1).
						runs(lambda src, ctx: add_location(src, ctx['name'], ctx['x'], ctx['y'], ctx['z'], ctx['dim'])).
						then(
							GreedyText('desc').
							runs(lambda src, ctx: add_location(src, ctx['name'], ctx['x'], ctx['y'], ctx['z'], ctx['dim'], ctx['desc']))
						)
					)))
				)
			)
		).
		then(
			Literal('del').then(
				QuotableText('name').runs(lambda src, ctx: delete_location(src, ctx['name']))
			)
		).
		then(
			Literal('info').then(
				QuotableText('name').runs(lambda src, ctx: show_location_detail(src, ctx['name']))
			)
		)
	)