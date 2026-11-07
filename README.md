# yuanhang41-openwrt

ZTE 远航 41（ZTE 7541N，P720S11 板，紫光展锐 UMS9620）的 OpenWrt 固件构建工程。
**实机全功能验证通过**：触摸、显示、充电电量、基带/板温、扬声器音频、LuCI、信息屏。

## 来源与致谢（fork 关系）

本仓库不是从零开始，而是在下列项目基础上做的 7541N 适配与修复：

| 上游 | 作者/组织 | 许可证 | 本仓库用了什么 |
| --- | --- | --- | --- |
| [e5-linux](https://github.com/sprd-linux-devs/e5-linux) | Enceka / sprd-linux-devs | MIT | yuanhang41s 设备 profile（本仓库 `overlay-devices/yuanhang41` 由其派生）、信息屏应用（含本仓库注入修复版 api.uc）、boot/installer 全套流程、`build.sh` 的编排对象 |
| [linux-lts-e5](https://github.com/Enceka/linux-lts-e5) | Enceka | GPL-2.0 | 内核基线（主线 6.18 LTS + UMS9620 平台支持），固定 commit 构建 |
| gcore_ts_v3 / zte_tpd | GalaxyCore / ZTE 出厂 Android 驱动源码 | GPL-2.0（内核模块语境） | 触摸驱动本体（`overlay/gcore_ts/`），本仓库移植到 6.18 并修复 |
| ZTE 厂商内核 | ZTE / 紫光展锐 | GPL-2.0（内核语境） | 触摸总线控制器 `overlay/spi_zte/`、USB PHY `overlay/phy-sprd-qogirn6pro.c` |
| OpenWrt 25.12.5 + 41S 发布包 | OpenWrt-CI / ZTE 工厂镜像 | 各自许可 | rootfs 与安装器的已验证二进制（`inputs` release 提供） |
| GalaxyCore 触摸固件 | GalaxyCore | 专有 | `overlay/gcore_firmware_skyworth.bin`（OTA 6.17.5.13，0-flash 设计每次开机 PRAM 下载必需，从厂商 Android 镜像逐字节提取） |

机型血缘：远航 41（7541N）与远航 41S（P720S11）是同一块 P720S11 板的两款机型，
触摸 IC 不同（41 = GalaxyCore GC7202H，41S = Sitronix ST7123），其余外设基本一致。

## 本仓库的增量（相对 e5-linux 的 41S profile）

* **触摸**：GC7202H 用 gcore_ts_v3 协议（非旧 GC7202 协议）；PRAM 固件下载 + CB 配置块握手；
  legacy ABS_X/ABS_Y 位注册与上报——libudev-zero 的 input 分类要求这两个位，否则触摸屏会被
  当成键盘（无声的失效，fd 开着但事件全丢）；GESTURE_KEY 移除避免误贴键盘标签
* **音频**：24 个 Unisoc 音频模块按 e5-audio-dsp 依赖序打进镜像（`lib/modules/<rel>/audio/`）
* **温度**：charger-manager 板温回退到内建 `board-thmzone`（bootloader DTB 缺 cm-thermal-zone）；
  信息屏 api.uc 补 UMS9620 的 nr0/nr1/nr 热区名
* **gcore WDT 心跳日志降级**（Android 同款正常行为，原映射误为 kern.err）
* **充电**：SGM4151x 在 DT 地址 0x6b（41S 强制 0x1a 在本机 NACK）；FGU 导出百分比/TYPE/STATUS
* **本地构建**：build.sh 支持 GitHub Actions 与任意 Linux 宿主（docker 容器内全离线可跑）
* **stage 脚本幂等化**（重入安全的内核源码补丁）

## 实机验证（7541N）

显示（720×1600）、触摸（滑动解锁/双指）、充电电量（CM+FGU 全链路）、
基带温度 44°C / 板温 43°C 真值、扬声器播放（hw:0,3 FE_FAST + AGDSP）、
5G SA 双卡、WiFi/BT、LuCI、信息屏（锁屏手势解锁、4 个应用）。

## 构建

```sh
# 宿主准备（或任意有 docker 的 Linux 机）
docker run -dt --name yh41build -v $PWD:/work -w /work ubuntu:24.04
# 容器内：装依赖 → 克隆三棵树 → 按“一次性准备”放好 inputs → 跑
bash build.sh kernel && bash build.sh rootfs && bash build.sh boot && bash build.sh repack
```

GitHub Actions：`.github/workflows/build-yuanhang41.yml`（手动触发）。
输入资产放 release tag `inputs`：41S 发布包 zip + 原厂 boot_b/misc dump（含校验单）。

## 风险边界

- ZTE / GalaxyCore / 紫光展锐 的商标、固件与工厂镜像归各自所有者；本仓库的专有二进制
  仅为设备 bring-up 互操作目的逐字节再分发，不附加任何许可
- 刷机前保留官方线刷救砖包与 GPT 备份；b 槽 Android 原封不动，启动失败自动回退
- 41S 发布包二进制在 41 上重打包使用为社区实践，未获 ZTE 背书

## 许可证

MIT（见 LICENSE）——本仓库自有代码与对 e5-linux（MIT）派生部分；
第三方组件按其自身许可证（内核 GPL-2.0、专有固件/工厂镜像如上声明）。
