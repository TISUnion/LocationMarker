import collections
import os
import sys
from threading import RLock
from typing import List

try:
	from plugins.command_builder import *
except ModuleNotFoundError:
	sys.path.append('plugins')
	# noinspection PyUnresolvedReferences
	from command_builder import *
from utils.rtext import *

Point = collections.namedtuple('Point', 'x y z')
Location = collections.namedtuple('Location', 'name description dimension position')


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


PREFIX = '!!loc'
ITEM_PER_PAGE = 10
HELP_MESSAGE = '''
--------- MCDR 路标插件 v20201231 ---------
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
STORAGE_FILE_PATH = os.path.join('plugins', 'LocationMarker', 'locations.json')

storage = LocationStorage(STORAGE_FILE_PATH)


def show_help(server, info):
	server.reply(info, HELP_MESSAGE)


def print_location(server, info, location):
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
	server.reply(info, RTextList(
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


def list_locations(server, info, keyword=None, page=None):
	matched_locations = []
	for loc in storage.get_locations():
		if keyword is None or loc.name.find(keyword) != -1 or (loc.description is not None and loc.description.find(keyword) != -1):
			matched_locations.append(loc)
	matched_count = len(matched_locations)
	if page is None:
		for loc in matched_locations:
			print_location(server, info, loc)
	else:
		left, right = (page - 1) * ITEM_PER_PAGE, page * ITEM_PER_PAGE
		for i in range(left, right):
			if 0 <= i < matched_count:
				print_location(server, info, matched_locations[i])

		has_prev = 0 < left < matched_count
		has_next = 0 < right < matched_count
		color = {False: RColor.dark_gray, True: RColor.gray}
		prev_page = RText('<-', color=color[has_prev])
		if has_prev:
			prev_page.c(RAction.run_command, '{} list {}'.format(PREFIX, page - 1)).h('点击显示上一页')
		next_page = RText('->', color=color[has_next])
		if has_next:
			next_page.c(RAction.run_command, '{} list {}'.format(PREFIX, page + 1)).h('点击显示下一页')

		server.reply(info, RTextList(
			prev_page,
			' 第§6{}§r页 '.format(page),
			next_page
		))
	if keyword is None:
		server.reply(info, '共有§6{}§r个路标'.format(matched_count))
	else:
		server.reply(info, '共找到§6{}§r个路标'.format(matched_count))


def add_location(server, info, name, x, y, z, dim, desc=None):
	if storage.contains(name):
		server.reply(info, '路标§b{}§r已存在，无法添加'.format(name))
		return
	try:
		location = Location(name, desc, dim, Point(x, y, z))
		storage.add(location)
	except Exception as e:
		server.reply(info, '路标§b{}§r添加§c失败§r: {}'.format(name, e))
	else:
		server.reply(info, '路标§b{}§r添加§a成功'.format(name))
		print_location(server, info, location)


def add_location_here(server, info, name, desc=None):
	if not info.is_player:
		server.reply(info, '仅有玩家允许使用本指令')
		return
	api = server.get_plugin_instance('PlayerInfoAPI')
	pos = api.getPlayerInfo(server, info.player, 'Pos')
	dim = api.getPlayerInfo(server, info.player, 'Dimension')
	if type(dim) is str:  # 1.16+
		dim = {'minecraft:overworld': 0, 'minecraft:the_nether': -1, 'minecraft:the_end': 1}[dim]
	add_location(server, info, name, pos[0], pos[1], pos[2], dim, desc)


def delete_location(server, info, name):
	loc = storage.remove(name)
	if loc is not None:
		server.reply(info, '已删除路标§b{}§r'.format(name))
		print_location(server, info, loc)
	else:
		server.reply(info, '未找到路标§b{}§r'.format(name))


class Executor:
	def __init__(self):
		self.server = None
		self.info = None
		self.executor = Literal(PREFIX). \
			run(lambda ctx: show_help(self.server, self.info)). \
			then(Literal('all').
				run(lambda ctx: list_locations(self.server, self.info))
			). \
			then(Literal('list').
				run(lambda ctx: list_locations(self.server, self.info)).
				then(Integer('page').
					run(lambda ctx: list_locations(self.server, self.info, page=ctx['page']))
				)
			). \
			then(Literal('search').
				then(QuotableText('keyword').
					run(lambda ctx: list_locations(self.server, self.info, keyword=ctx['keyword'])).
					then(Integer('page').
						run(lambda ctx: list_locations(self.server, self.info, keyword=ctx['keyword'], page=ctx['page']))
					)
				)
			). \
			then(Literal('add').
				then(QuotableText('name').
					then(Literal('here').
						run(lambda ctx: add_location_here(self.server, self.info, ctx['name'])).
						then(GreedyText('desc').
							run(lambda ctx: add_location_here(self.server, self.info, ctx['name'], ctx['desc']))
						)
					).
					then(Number('x').
						then(Number('y').
							then(Number('z').
								then(Integer('dim').in_range(-1, 1).
									run(lambda ctx: add_location(self.server, self.info, ctx['name'], ctx['x'], ctx['y'], ctx['z'], ctx['dim'])).
									then(GreedyText('desc').
										run(lambda ctx: add_location(self.server, self.info, ctx['name'], ctx['x'], ctx['y'], ctx['z'], ctx['dim'], ctx['desc']))
									)
								)
							)
						)
					)
				)
			). \
			then(Literal('del').
				then(QuotableText('name').
					run(lambda ctx: delete_location(self.server, self.info, ctx['name']))
				)
			)

	def execute(self, server, info, command):
		self.server = server
		self.info = info
		self.executor.execute(command)


executor = Executor()


def on_user_info(server, info):
	try:
		executor.execute(server, info, info.content)
	except UnknownRootArgument:
		pass
	except CommandError as e:
		server.reply(info, RText(e, color=RColor.red))


def on_load(server, old_inst):
	server.add_help_message(PREFIX, '路标管理')
	global storage
	if hasattr(old_inst, 'storage') and type(old_inst.storage) == type(storage):
		storage.lock = old_inst.storage.lock
	storage.load(server.logger)
