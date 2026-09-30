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
