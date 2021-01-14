import collections
import json
import os
from threading import RLock
from typing import List, Callable, Any

from mcdreforged.api.all import *


PLUGIN_METADATA = {
	'id': 'location_marker',
	'version': '1.0.0',
	'name': 'Location Marker',
	'description': 'A server side waypoint manager',
	'author': 'Fallen_Breath',
	'link': 'https://github.com/TISUnion/LocationMarker',
	'dependencies': {
		'mcdreforged': '>=1.0.0-alpha.8',
	}
}

Point = collections.namedtuple('Point', 'x y z')
Location = collections.namedtuple('Location', 'name description dimension position')

PREFIX = '!!loc'
ITEM_PER_PAGE = 10
HELP_MESSAGE = '''
--------- MCDR 路标插件 v20210101 ---------
一个位于服务端的路标管理插件
§7{0}§r 显示此帮助信息
§7{0} list §6[<可选页号>]§r 列出所有路标
§7{0} search §b<关键字> §6[<可选页号>]§r 搜索坐标，返回所有匹配项
§7{0} add §b<路标名称> §e<x> <y> <z> <维度id> §6[<可选注释>]§r 加入一个路标
§7{0} add §b<路标名称> §ehere §6[<可选注释>]§r 加入自己所处位置、维度的路标
§7{0} del §b<路标名称>§r 删除路标，要求全字匹配
其中：
当§6可选页号§r被指定时，将以每{1}个路标为一页，列出指定页号的路标
§b关键字§r以及§b路标名称§r为不包含空格的一个字符串，或者一个被""括起的字符串
§e维度id§r参考: 主世界为§e0§r, 下界为§e-1§r, 末地为§e1§r
'''.strip().format(PREFIX, ITEM_PER_PAGE)
STORAGE_FILE_PATH = os.path.join('config', PLUGIN_METADATA['id'], 'locations.json')


class LocationStorage:
	def __init__(self, file_path):
		self.file_path = file_path
		self.locations = []  # type: List[Location]
		self.name_map = {}
		self.lock = RLock()

	def save(self):
		with self.lock:
			output = []
			for loc in self.locations:
				output.append({
					'name': loc.name,
					'dim': loc.dimension,
					'desc': loc.description,
					'pos': {
						'x': loc.position.x,
						'y': loc.position.y,
						'z': loc.position.z
					}
				})
			with open(self.file_path, 'w', encoding='utf8') as handle:
				handle.write(json.dumps(output, indent=2, ensure_ascii=False))

	def load(self, logger=None):
		with self.lock:
			self.locations = []
			needs_overwrite = False
			if not os.path.isfile(self.file_path):
				os.mkdir(os.path.dirname(self.file_path))
				needs_overwrite = True
			else:
				with open(self.file_path, 'r', encoding='utf8') as handle:
					try:
						for loc in json.load(handle):
							self.__add(Location(
								name=loc['name'],
								description=loc.get('desc', None),
								dimension=loc['dim'],
								position=Point(loc['pos']['x'], loc['pos']['y'], loc['pos']['z'])
							))
					except Exception as e:
						(logger.error if logger is not None else print)('Fail to load {}: {}'.format(self.file_path, e))
						needs_overwrite = True
			if needs_overwrite:
				self.save()

	def get(self, name):
		with self.lock:
			return self.name_map.get(name, None)

	def get_locations(self):
		with self.lock:
			return self.locations.copy()

	def contains(self, name):
		with self.lock:
			return name in self.name_map

	def __add(self, location):
		with self.lock:
			existed = self.get(location.name)
			if existed:
				return False
			else:
				self.locations.append(location)
				self.name_map[location.name] = location
				return True

	def add(self, location):
		ret = self.__add(location)
		self.save()
		return ret

	def __remove(self, target_name):
		with self.lock:
			loc = self.get(target_name)
			if loc is not None:
				self.locations.remove(loc)
				self.name_map.pop(loc.name)
				return loc
			else:
				return None

	def remove(self, target_name):
		ret = self.__remove(target_name)
		self.save()
		return ret


storage = LocationStorage(STORAGE_FILE_PATH)


def show_help(source: CommandSource):
	source.reply(HELP_MESSAGE)


def print_location(location, printer: Callable[[RTextBase], Any]):
	x = location.position.x
	y = location.position.y
	z = location.position.z
	name_text = RText(location.name)
	if location.description is not None:
		name_text.h(location.description)
	dimension_convert = {0: 'minecraft:overworld', -1: 'minecraft:the_nether', 1: 'minecraft:the_end'}
	dim_key = dimension_convert[location.dimension]
	dimension_color = {0: RColor.dark_green, -1: RColor.dark_red, 1: RColor.dark_purple}
	dimension_translation = {
		0: 'createWorld.customize.preset.overworld',
		-1: 'advancements.nether.root.title',
		1: 'advancements.end.root.title'
	}
	printer(RTextList(
		'§7-§r ',
		name_text,
		' ',
		RText('[{}, {}, {}]'.format(round(x, 1), round(y, 1), round(z, 1)), color=RColor.green).
			c(RAction.suggest_command, '/execute in {} run tp {} {} {}'.format(dim_key, x, y, z)).
			h('点击以传送'),
		' §7@§r ',
		RTextTranslation(dimension_translation[location.dimension], color=dimension_color[location.dimension]).
			h(dim_key)
	))


def reply_location(source: CommandSource, location):
	print_location(location, lambda msg: source.reply(msg))


def broadcast_location(server: ServerInterface, location):
	print_location(location, lambda msg: server.say(msg))


def list_locations(source: CommandSource, *, keyword=None, page=None):
	matched_locations = []
	for loc in storage.get_locations():
		if keyword is None or loc.name.find(keyword) != -1 or (loc.description is not None and loc.description.find(keyword) != -1):
			matched_locations.append(loc)
	matched_count = len(matched_locations)
	if page is None:
		for loc in matched_locations:
			reply_location(source, loc)
	else:
		left, right = (page - 1) * ITEM_PER_PAGE, page * ITEM_PER_PAGE
		for i in range(left, right):
			if 0 <= i < matched_count:
				reply_location(source, matched_locations[i])

		has_prev = 0 < left < matched_count
		has_next = 0 < right < matched_count
		color = {False: RColor.dark_gray, True: RColor.gray}
		prev_page = RText('<-', color=color[has_prev])
		if has_prev:
			prev_page.c(RAction.run_command, '{} list {}'.format(PREFIX, page - 1)).h('点击显示上一页')
		next_page = RText('->', color=color[has_next])
		if has_next:
			next_page.c(RAction.run_command, '{} list {}'.format(PREFIX, page + 1)).h('点击显示下一页')

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
		location = Location(name, desc, dim, Point(x, y, z))
		storage.add(location)
	except Exception as e:
		source.reply('路标§b{}§r添加§c失败§r: {}'.format(name, e))
	else:
		source.get_server().say('路标§b{}§r添加§a成功'.format(name))
		broadcast_location(source.get_server(), location)


def add_location_here(source: CommandSource, name, desc=None):
	if not isinstance(source, PlayerCommandSource):
		source.reply('仅有玩家允许使用本指令')
		return
	api = source.get_server().get_plugin_instance('PlayerInfoAPI')
	pos = api.getPlayerInfo(source.player, 'Pos')
	dim = api.getPlayerInfo(source.player, 'Dimension')
	if type(dim) is str:  # 1.16+
		dim = {'minecraft:overworld': 0, 'minecraft:the_nether': -1, 'minecraft:the_end': 1}[dim]
	add_location(source, name, pos[0], pos[1], pos[2], dim, desc)


def delete_location(source: CommandSource, name):
	loc = storage.remove(name)
	if loc is not None:
		source.get_server().say('已删除路标§b{}§r'.format(name))
		broadcast_location(source.get_server(), loc)
	else:
		source.reply('未找到路标§b{}§r'.format(name))


def on_load(server: ServerInterface, old_inst):
	server.register_help_message(PREFIX, '路标管理')
	global storage
	if hasattr(old_inst, 'storage') and type(old_inst.storage) == type(storage):
		storage.lock = old_inst.storage.lock
	storage.load(server.logger)
	server.register_command(
		Literal(PREFIX).
		runs(show_help).
		then(
			Literal('all').runs(lambda src: list_locations(src))
		).
		then(
			Literal('list').runs(lambda src: list_locations(src)).
			then(
				Integer('page').runs(lambda src, ctx: list_locations(src, page=ctx['page']))
			)
		).
		then(
			Literal('search').then(
				QuotableText('keyword').runs(lambda src, ctx: list_locations(src, keyword=ctx['keyword'])).
				then(
					Integer('page').runs(lambda src, ctx: list_locations(src, keyword=ctx['keyword'], page=ctx['page']))
				)
			)
		).
		then(
			Literal('add').then(
				QuotableText('name').
				then(
					Literal('here').
					runs(lambda src, ctx: add_location_here(src, ctx['name'])).
					then(
						GreedyText('desc').runs(lambda src, ctx: add_location_here(src, ctx['name'], ctx['desc']))
					)
				).
				then(
					Number('x').then(
						Number('y').then(
							Number('z').then(
								Integer('dim').in_range(-1, 1).
								runs(lambda src, ctx: add_location(src, ctx['name'], ctx['x'], ctx['y'], ctx['z'], ctx['dim'])).
								then(
									GreedyText('desc').
									runs(lambda src, ctx: add_location(src, ctx['name'], ctx['x'], ctx['y'], ctx['z'], ctx['dim'], ctx['desc']))
								)
							)
						)
					)
				)
			)
		).
		then(
			Literal('del').then(
				QuotableText('name').
				runs(lambda src, ctx: delete_location(src, ctx['name']))
			)
		)
	)
