# yuanhang41 OpenWrt 云端构建

为本机远航41（ZTE 7541N，P720S11 板）自编 OpenWrt 固件。
内核用 e5-linux 的 yuanhang41s profile 从源码构建（同一块 UMS9620 板），
OpenWrt rootfs 与安装器复用 41S 发布包的已验证二进制，重打包为 7541N 身份。

## 一次性准备

1. 在本仓库创建 release tag `inputs`，上传两个资产：
   - `yuanhang41s-package.zip` — 41S 完整安装包 ZIP（yuanhang41s-openwrt-25.12.5-*.zip，约 275 MB）
   - `yuanhang41-stock-dumps.zip` — 含 `boot_b.img`（64 MiB 原厂 boot_b）、
     `misc-head.bin`（4096 字节）、`SHA256SUMS`（前两个文件的校验单）
2. Actions 页面手动触发 **Build yuanhang41 OpenWrt**。

## 产物

Artifact `yuanhang41-openwrt-package`：`yuanhang41-openwrt-25.12.5-*.zip`
（可直接用包内 OpenWrt-Installer.exe 安装，机型识别 ZTE 7541N）。

## 风险边界

- 41S 发布包未实机验证；41 上的屏幕/充电/触摸未实测。
- 启动失败两次自动回退 Android；b 槽 Android 原封不动。
- 刷机前保留官方线刷救砖包与 GPT 备份。
