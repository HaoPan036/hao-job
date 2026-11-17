# 工具共用模块

`haojob_common` 是各工具共用的小型 Python 包，只用 Python 3.10+ 标准库，不联网、不读取 private 文件，也没有命令行入口。只有各工具本应完全一致的行为才放在这里；同名但语义不同的函数仍留在各自工具中。

目前包含：

- `text.py`：文本清理和岗位编号整词匹配。
- `urls.py`：Job Radar 去重与投递同步共用的链接比较形式。它的输出也是采集器 SQLite 已见状态和 changedetection 状态中的键，修改任何已有输入的输出都会使这些键失效；测试固定了现有输出。同步只在比较时使用它，不改写台账中的链接。
- `paths.py`：运行材料路径检查。路径任何一级都不能是符号链接（macOS 的 `/var`、`/tmp` 系统别名除外）；位于 Git 工作区时必须被忽略且未跟踪；不在 Git 中时，只有调用方明确允许才接受。上级目录尚不存在时也能检查。各工具保留原有范围：Job Radar 的 `radar.py`、`collect.py` 接受用户选定的包外目录，recruiting-sync、changedetection 桥接和安装器仍要求在 Git 仓库内。`application-record` 使用基于文件描述符的独立检查，不经过本模块。

工具以脚本方式运行（`python3 tools/<工具>/<脚本>.py`），启动时把 `tools/` 目录加入 `sys.path` 后导入本包，并关闭字节码缓存写入。原有函数名在各工具模块中保留为别名，旧调用方式不变。复制单个工具脚本到别处时，要把 `haojob_common/` 一起放到脚本目录的上一级。

```sh
python3 -m unittest discover -s tools/haojob_common/tests -v
```
