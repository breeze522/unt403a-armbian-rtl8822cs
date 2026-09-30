# 九联 UNT403A 刷 Armbian 并修复 RTL8822CS 无线网卡（含安装到 eMMC）

本文记录给九联 UNT403A 机顶盒刷 Armbian 的全过程。重点有两个：一是修好板载无线网卡 RTL8822CS，二是把系统从 U 盘装进内置 eMMC，最后拔掉 U 盘直接开机。

所有步骤都在真机上验证过。

---

## 一、硬件信息

- 型号：九联 UNT403A 网络机顶盒
- 主控：晶晨 Amlogic S905L3A，架构代号 g12a
- 内存：2GB
- 内置存储：16GB eMMC
- 有线网口：100M
- 无线芯片：Realtek RTL8822CS，走 SDIO 接口，支持双频 11ac（芯片还带蓝牙，本文只处理 WiFi）

同方案、设备树和引导可以通用的盒子：M401A、B863AV3.2-M。

---

## 二、需要准备的东西

- 一个 U 盘（用来启动和装系统）
- 一台 Windows 电脑
- 一根网线（盒子连电脑或路由器，安装阶段先用有线）
- 烧录工具：balenaEtcher 或 Rufus
- SSH 工具：MobaXterm
- 系统镜像（ophub 制作的 amlogic 版本），本次使用的文件名：

```
Armbian_26.11.0_amlogic_s905l3a-m401a_bookworm_6.12.109_server_2026.09.14.img.gz
```

镜像下载地址（ophub 发布页）：
`https://github.com/ophub/amlogic-s9xxx-armbian/releases`

下载时认准 tag 里带 `s905l3a-m401a` 的 server 版本。

---

## 三、烧录 U 盘

1. 把下载的 `.img.gz` 用烧录工具写进 U 盘（Etcher 可以直接读 gz，不用解压）。
2. 烧完后 U 盘会有两个分区：一个小的启动分区（FAT），一个大的根分区（ext4）。这是正常现象，Windows 可能提示格式化，点取消，不要格。

---

## 四、U 盘启动并连接

1. U 盘插到盒子 USB 口。
2. 网线接好（这一步先用有线网，无线还没修）。
3. 给盒子上电。盒子会优先从 U 盘启动。
4. 在电脑上查看盒子拿到的 IP。可以登录路由器看新设备，也可以用扫描工具。
   - 如果电脑网口直连盒子，可以在 Windows 上开启「网络共享（ICS）」，让盒子通过电脑上网。
5. 打开 MobaXterm，新建 SSH 会话：

```
ssh root@盒子的IP
```

6. 第一次登录会让你设置 root 密码，按提示操作。

登录后先确认有线正常：

```bash
ip -br addr
```

能看到 eth0 是 UP，并且拿到了 IP，就说明有线通了。

---

## 五、先找无线网卡不能用的原因

很多人以为无线不能用是缺驱动。这台机器不是。

### 5.1 驱动其实已经有了

内核 6.12.109 已经内置了 rtw88 驱动，其中就包括 8822CS。可以查一下：

```bash
ls /lib/modules/$(uname -r)/kernel/drivers/net/wireless/realtek/rtw88/
```

能看到 `rtw88_8822cs.ko` 等文件。

### 5.2 固件也齐全

```bash
ls /lib/firmware/rtw88/ | grep 8822c
```

能看到这几个文件：

```
rtw8822c_fw.bin
rtw8822cs_fw.bin
rtw8822c_wow_fw.bin
```

### 5.3 真正的原因：设备树把 SDIO 端口关了

RTL8822CS 挂在 SDIO 总线 `sd_emmc_a` 上，对应控制器是 `mmc@ffe03000`（也叫 mmc0）。在出厂设备树里，这个端口的状态是 `disabled`。端口没开，芯片就不上电，系统自然扫不到无线网卡。

先反编译设备树看一眼：

```bash
cd /boot/dtb/amlogic
cp meson-g12a-s905l3a-m401a.dtb /root/m401a-orig.dtb      # 先备份原版
dtc -I dtb -O dts -o /tmp/m401a.dts meson-g12a-s905l3a-m401a.dtb
```

> 如果提示没有 dtc 命令，先装：`apt update && apt install -y device-tree-compiler`

在反编译出来的 `/tmp/m401a.dts` 里找到 `mmc@ffe03000`，会看到 `status = "disabled";`。这就是问题所在。

---

## 六、修改设备树（核心步骤）

要做两件事：

1. 把 `mmc@ffe03000` 这个 SDIO 端口打开；
2. 新增一个上电节点 `wifi_pwrseq`，用 GPIOX_6 这根脚给无线模块上电（低电平有效）。

### 6.1 关键参数（本机实测）

| 用途 | 值 |
|---|---|
| 主控 GPIO 控制器（phandle） | `0x30` |
| WiFi 上电/复位脚 | GPIOX_6，即 bank 第 22 脚（`0x16`），低电平有效（末位 `0x01`） |
| SDIO 电源 vmmc | vddao_3v3（phandle `0x31`） |
| SDIO IO 电源 vqmmc | vddao_1v8（phandle `0x0e`） |
| SDIO 引脚组 pinctrl-0 | phandle `0xb3` |
| 时钟门控引脚组 pinctrl-1 | phandle `0xb4` |
| 总线频率上限 | 100MHz（`0x5f5e100`） |

> 注意：上面这些 phandle 数字是针对这个版本的 m401a 设备树实测出来的。如果你用的是别的日期、别的版本的 dtb，数字可能不一样，要自己在 dts 里核对，不能照抄。

### 6.2 用脚本打补丁

在电脑上新建文件 `patch_wifi.py`，内容如下，然后传到盒子 `/tmp/patch_wifi.py`：

```python
import re
with open('/tmp/m401a.dts') as f:
    dts = f.read()

def build(ind):
    a = ind
    b = ind + '\t'
    lines = [
 a+'wifi_pwrseq: wifi-pwrseq {',
 b+'compatible = "mmc-pwrseq-simple";',
 b+'reset-gpios = <0x30 0x16 0x01>;',
 b+'post-power-on-delay-ms = <0xc8>;',
 a+'};',
 a+'mmc@ffe03000 {',
 b+'compatible = "amlogic,meson-axg-mmc";',
 b+'reg = <0x00 0xffe03000 0x00 0x800>;',
 b+'interrupts = <0x00 0xbd 0x04>;',
 b+'status = "okay";',
 b+'clocks = <0x02 0x21 0x02 0x3c 0x02 0x02>;',
 b+'clock-names = "core\\0clkin0\\0clkin1";',
 b+'resets = <0x05 0x2c>;',
 b+'assigned-clocks = <0x02 0x3c>;',
 b+'assigned-clock-rates = <0x16e3600>;',
 b+'amlogic,dram-access-quirk;',
 b+'pinctrl-0 = <0xb3>;',
 b+'pinctrl-1 = <0xb4>;',
 b+'pinctrl-names = "default\\0clk-gate";',
 b+'#address-cells = <0x01>;',
 b+'#size-cells = <0x00>;',
 b+'bus-width = <0x04>;',
 b+'cap-sd-highspeed;',
 b+'cap-sdio-irq;',
 b+'max-frequency = <0x5f5e100>;',
 b+'non-removable;',
 b+'disable-wp;',
 b+'keep-power-in-suspend;',
 b+'mmc-pwrseq = <&wifi_pwrseq>;',
 b+'vmmc-supply = <0x31>;',
 b+'vqmmc-supply = <0x0e>;',
 b+'phandle = <0x133>;',
 a+'};',
    ]
    return '\n'.join(lines) + '\n'

pat = r'(?m)^(\s*)mmc@ffe03000 \{.*?\n\1\};'
dts2, n = re.subn(pat, lambda m: build(m.group(1)), dts, count=1, flags=re.DOTALL)
print('replacements:', n)
assert n == 1
with open('/tmp/m401a_new.dts', 'w') as f:
    f.write(dts2)
print('OK written /tmp/m401a_new.dts')
```

运行补丁并重新编译成 dtb：

```bash
python3 /tmp/patch_wifi.py
dtc -I dts -O dtb -o /tmp/m401a_new.dtb /tmp/m401a_new.dts
```

> dtc 编译时可能有一堆 warning，多数是单元名、时钟方面的提醒，不影响使用。只要最后生成了 dtb 文件就行。

### 6.3 替换设备树

```bash
cp /tmp/m401a_new.dtb /boot/dtb/amlogic/meson-g12a-s905l3a-m401a.dtb
sync
```

### 6.4 重启

```bash
reboot
```

重启时 SSH 会断开，等盒子重新从 U 盘启动后再连回来。

---

## 七、验证无线网卡

重新连上后，先看启动日志有没有识别到 SDIO 无线芯片：

```bash
dmesg | grep -iE "rtw|8822|sdio|mmc0"
```

正常的话能看到类似「new high speed SDIO card」、加载固件 9.9.11、创建 wlan0 的信息。

打开 wlan0：

```bash
ip link set wlan0 up
```

扫描热点：

```bash
nmcli dev wifi list
```

连接你的 WiFi（把名字和密码换成自己的）：

```bash
nmcli dev wifi connect "你的WiFi名" password "你的WiFi密码"
```

查看结果：

```bash
ip -br addr show wlan0
nmcli dev status
```

wlan0 显示 UP，并拿到 IP 地址，就说明无线修好了。

---

## 八、踩坑记录（很重要，建议先看）

### 8.1 G12 系列 SDIO 有硬件缺陷

晶晨 G12/G12A 系列的 SDIO 控制器有已知问题：它不能正常做 DMA，大数据要走控制器内部 SRAM，单次传输有限制（约 1536 字节）。这个问题对应 CVE-2023-52611。

实际表现是：在执行扫描（`iw dev wlan0 scan`）这种一次性传大量数据的操作时，偶尔会内核崩溃，盒子自动重启。

### 8.2 不要删 `amlogic,dram-access-quirk`

设备树里有一行 `amlogic,dram-access-quirk`，它正是用来处理上面这个内存访问问题的。

我试过把它删掉，结果扫描照样崩溃，有时连 wlan0 都不创建。**所以这一行必须保留。**

### 8.3 保留 quirk 的版本才是稳定版

保留 `amlogic,dram-access-quirk`、频率设 100MHz、用 GPIOX_6 上电的这一版，实测可以稳定联网：wlan0 正常 UP，能关联热点，能拿到 IPv4 和 IPv6，数据收发正常。

早期遇到的扫描崩溃，和当时反复加载/卸载模块、状态残留有关。正常启动后直接连接，没有再出问题。

### 8.4 先备份，随时能回退

改设备树之前一定先备份原版和每一个能用的版本。建议在盒子上建一个目录：

```bash
mkdir -p /root/dtb-backup
```

把确认能用的 dtb、对应的 dts、一份说明都放进去。再用 scp 下载到电脑一份，做双保险。

本次验证可用的文件大小：

- 可用 dtb：79358 字节
- 对应 dts：97123 字节

如果改坏了，用备份覆盖回 `/boot/dtb/amlogic/meson-g12a-s905l3a-m401a.dtb`，重启即可恢复。

---

## 九、把系统安装到内置 eMMC

无线确认稳定后，就可以把 U 盘里这套（带无线修复的）系统装进 eMMC。

ophub 镜像自带安装脚本，直接运行：

```bash
armbian-install
```

脚本会自动检测到 eMMC（本机是 `/dev/mmcblk2`），然后列出支持的设备让你选。

### 9.1 选设备

在设备列表里找到这一行：

```
ID    SOC       MODEL            DTB
306   s905l3a   M401A,UNT403A    meson-g12a-s905l3a-m401a.dtb
```

输入 `306` 并回车。

脚本会确认以下信息：

- Model：M401A,UNT403A,B863AV3.2-M
- FDTFILE：meson-g12a-s905l3a-m401a.dtb
- UBOOT_OVERLOAD：u-boot-e900v22c.bin

### 9.2 选文件系统

接着选根文件系统类型：

```
1  ext4
2  btrfs
```

输入 `1`，选 ext4。ext4 最稳定通用，机顶盒用它就够了。

### 9.3 等待安装

脚本会自动完成这些事：

1. 备份原有引导；
2. 用 ampart 重新给 eMMC 分区；
3. 写入引导（u-boot）；
4. 格式化启动分区和根分区；
5. 把 U 盘里的启动文件和整个根文件系统复制到 eMMC；
6. 生成新的 fstab。

复制过程中会刷大量日志。如果看到外语（本次是西班牙语）的时间戳提示，比如「en el futuro」，那只是时间戳警告，不影响安装，不用管。

最后看到这一行就表示成功：

```
[ SUCCESS ] Installation completed successfully.
```

### 9.4 关机前再验证一次 eMMC 上的设备树

为了确保装进去的确实是无线可用版，关机前挂载 eMMC 启动分区检查：

```bash
mount /dev/mmcblk2p1 /mnt
ls -l /mnt/dtb/amlogic/meson-g12a-s905l3a-m401a.dtb
grep -iE "FDT" /mnt/uEnv.txt
umount /mnt
sync
```

要确认两点：

1. dtb 文件大小是 **79358 字节**（无线可用版，不是原版）；
2. uEnv.txt 里是 `FDT=/dtb/amlogic/meson-g12a-s905l3a-m401a.dtb`。

两点都对，才能关机。

> 说明：安装脚本不会去网上重新下载原版设备树。它是把当前 U 盘运行的整套系统复制到 eMMC，U 盘里的 dtb 已经是改好的版本，所以无线修复会一起带过去。脚本里的 FDTFILE 只是告诉引导去加载哪个文件名。

---

## 十、拔掉 U 盘，从 eMMC 启动

1. 在终端执行关机：

```bash
poweroff
```

2. 等盒子完全断电（指示灯熄灭）。
3. **拔掉 U 盘**。
4. 重新给盒子上电，U 盘保持拔掉。
5. 等约 1 分钟，让盒子从 eMMC 启动。

---

## 十一、最终验证

重新连上盒子（IP 可能变化，以实际为准），执行：

```bash
lsblk
ip -br addr
nmcli dev status
```

要确认三件事：

1. `lsblk` 里**只有 mmcblk2，没有 sda**，说明 U 盘已经不在，系统确实跑在 eMMC 上；根分区 `/` 挂在 mmcblk2p2，容量约 14G。
2. eth0 是 UP，有线正常。
3. **wlan0 是 UP，并且自动连回了之前的 WiFi**，拿到了 IP。

本次实测结果：

- 根分区：eMMC，约 14G，占用 13%
- eth0：UP，192.168.137.183
- wlan0：UP，10.160.209.23，自动连接到热点，IPv4 和 IPv6 都正常

到这里就全部完成了。以后开机不用 U 盘，有线无线都能用。

---

## 十二、关键参数速查表

| 项目 | 值 |
|---|---|
| 盒子型号 | 九联 UNT403A |
| 主控 | Amlogic S905L3A（g12a） |
| 内存 / 存储 | 2GB / 16GB eMMC |
| 无线芯片 | Realtek RTL8822CS（SDIO） |
| SDIO 控制器 | mmc@ffe03000（mmc0 / sd_emmc_a） |
| eMMC 设备 | /dev/mmcblk2 |
| 安装时设备 ID | 306 |
| 根文件系统 | ext4 |
| 引导文件 | u-boot-e900v22c.bin |
| 设备树文件 | meson-g12a-s905l3a-m401a.dtb |
| WiFi 上电脚 | GPIOX_6（低电平有效） |
| 可用 dtb 大小 | 79358 字节 |
| 内核版本 | 6.12.109-ophub |
| 系统版本 | Armbian 26.11.0，Debian 12 bookworm |

---

## 十三、常见问题

**Q：改完设备树重启，wlan0 还是没有。**
A：先看 `dmesg | grep -iE "mmc0|sdio|rtw"`。如果连「new SDIO card」都没有，说明 SDIO 端口没开或上电脚不对，检查 dts 里 status 是否 okay、pwrseq 的 GPIO 是否正确。如果能识别芯片但没有 wlan0，多半是固件没加载，确认 `/lib/firmware/rtw88/` 里的 8822c 固件齐全。

**Q：一扫 WiFi 就崩溃重启。**
A：这是 G12 SDIO 的已知硬件问题。确认设备树里保留了 `amlogic,dram-access-quirk`，频率不要设太高（100MHz）。重启后不要反复扫描，直接连接热点即可。

**Q：想恢复原来的系统。**
A：把备份的原版 dtb 覆盖回去再重启，可以恢复 U 盘系统的原状。但 eMMC 一旦安装就会被覆盖，原来的安卓系统需要另找原厂固件重刷，安装前请想清楚。

**Q：蓝牙能用吗？**
A：RTL8822CS 还带蓝牙，一般挂在 uart_A 上，需要另外配置使能脚和唤醒脚。本次没有处理蓝牙，只保证 WiFi。

---

## 十四、参考链接

- ophub 镜像发布页：https://github.com/ophub/amlogic-s9xxx-armbian/releases
- ophub 项目主页：https://github.com/ophub/amlogic-s9xxx-armbian
- 型号 / 设备树 / 引导对照表：
  https://raw.githubusercontent.com/ophub/amlogic-s9xxx-armbian/main/build-armbian/armbian-files/common-files/etc/model_database.conf
- 主线内核 g12a + RTL8822CS 参考设备树（Freebox Player Pop）：
  `meson-g12a-fbx8am.dts`、`meson-g12a-fbx8am-realtek.dtso`
- G12 SDIO 问题 CVE 说明：https://nvd.nist.gov/vuln/detail/cve-2023-52611
- Banana Pi CM4（同芯片方案）无线讨论：
  https://forum.armbian.com/topic/44899-slow-wifi-speeds-on-banana-pi-cm4/
