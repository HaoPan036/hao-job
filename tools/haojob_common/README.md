# 工具共用模块

`haojob_common` 是各工具共用的小型 Python 包，只用 Python 3.10+ 标准库，不联网、不读取 private 文件，也没有命令行入口。只有各工具本应完全一致的行为才放在这里；同名但语义不同的函数仍留在各自工具中。

工具以脚本方式运行（`python3 tools/<工具>/<脚本>.py`），启动时把 `tools/` 目录加入 `sys.path` 后导入本包，并关闭字节码缓存写入。原有函数名在各工具模块中保留为别名，旧调用方式不变。复制单个工具脚本到别处时，要把 `haojob_common/` 一起放到脚本目录的上一级。

```sh
python3 -m unittest discover -s tools/haojob_common/tests -v
```
