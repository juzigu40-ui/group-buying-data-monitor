# 实时舆情输入规范

- 门店：凤状元·江西小炒·非遗米粉(食宝街店)
- 城市：北京
- 调度频率：每天 10:00-21:00 每小时一次
- OpenClaw 角色：负责抓取或执行，把原始内容写入下面三个标准 JSON 文件
- 本系统角色：负责统一字段、门店命中、噪音过滤、去重和交付输出

## 标准输入文件

- `public_xiaohongshu.json`
- `public_douyin.json`
- `public_shipinhao.json`

## 必填字段

- `content_id`
- `platform`
- `title`
- `content`
- `author_name`
- `url`

## 推荐字段

- `poi_name`
- `published_at`
- `like_count`
- `comment_count`
- `share_count`
- `author_level`
- `ip_location`
- `topic_tags`
- `favorite_count`
- `source_store_id`
- `source_store_name`
- `source_channel`
- `campaign_name`
- `content_library_tag`

## 如果要做门店KPI监管，这些字段建议视为必填

- `source_store_id`
- `source_store_name`
- `source_channel`
- `campaign_name`
- `content_library_tag`
- `published_at`

## 说明

1. 不是模糊的“OpenClaw+skills”，而是固定输入文件、固定字段和固定输出。
2. 客户最终看的是 `signal_watchboard.md`、`signal_report.txt` 和交付说明页。
3. 后续如果新增采集方式，只要继续写入这三个文件，不需要重做客户使用方式。
4. 如果内容来自门店碰一碰、内容库或活动导流链路，优先补 `source_store_id` / `source_store_name`，系统会按门店直连记账统计每日达标情况。
5. 如果老板要把这件事当门店KPI考核，建议规则里打开 `require_source_store`，只统计门店直连内容。
6. 如果缺少 `published_at`，这条内容仍可被识别，但不会被稳妥计入“今日达标数”。
