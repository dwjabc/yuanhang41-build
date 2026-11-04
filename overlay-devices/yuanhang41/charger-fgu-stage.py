"""yuanhang41 charger + fuel-gauge display adaptation.

Runs after the 41S prepare stack:

1. The 41S charger.py forces the SQC charger onto I2C 0x1a (that unit's
   wiring). This unit (7541N) answers the SGM4151x ID at the DT address
   0x6b -- verified live (REG_B=0x14), while 0x1a NACKs -- so drop the
   alias switch, keep the DT address and gate on the observed ID.
2. Early-boot I2C may not be settled when the charger probes; return
   -EPROBE_DEFER so the driver core retries instead of dying once.
3. The vendor UMP9620 fuel gauge reports per-mille capacity and hides
   TYPE/STATUS, which defeats the rootfs battery pipeline (unisoc-battery
   snapshot, e5-charge rpcd). Export percent capacity, Battery type and
   the CM-written charging status.
"""
from pathlib import Path


def apply(kernel):
    kernel = Path(kernel)

    charger = kernel / 'drivers' / 'power' / 'supply' / 'bq2560x-charger.c'
    s = charger.read_text(encoding='utf-8')

    old = ('\t/* P720S11 SGM41513: factory driver switches this DT alias to 0x1a. */\n'
           '\tclient->addr = 0x1a;\n')
    if old in s:
        s = s.replace(old, '\t/* yuanhang41: this unit answers at the DT address (0x6b). */\n', 1)
    elif 'client->addr = 0x1a;' in s:
        raise ValueError('41S alias-switch block changed; refusing blind patch')

    old = '(val >> 3) != 0 || client->addr != 0x1a'
    new = '(val & 0x7c) != 0x14 || client->addr != 0x6b'
    if s.count(old) != 1:
        raise ValueError('41S charger ID gate anchor changed')
    s = s.replace(old, new, 1)

    old = ('\tret = bq2560x_read(info, BQ2560X_REG_B, &val);\n'
           '\tif (ret < 0) return ret;')
    new = ('\tret = bq2560x_read(info, BQ2560X_REG_B, &val);\n'
           '\tif (ret < 0)\n'
           '\t\treturn -EPROBE_DEFER; /* I2C may lag early boot; let the core retry */')
    if s.count(old) != 1:
        raise ValueError('charger probe read anchor changed')
    s = s.replace(old, new, 1)

    s = s.replace('"41S-SGM41513"', '"yh41-SGM41513"', 1)

    # hw_init register writes NACK for up to ~2 minutes on this unit while
    # reads already work at 4.5s; the deferred-probe queue gives up around
    # 30s. Probe asynchronously and spin here until the write path settles.
    old = '\tinfo->client = client;\n\tinfo->dev = dev;'
    new = ('\tinfo->client = client;\n'
           '\tinfo->dev = dev;\n'
           '\tdevice_enable_async_probe(dev);')
    if s.count(old) != 1:
        raise ValueError('probe info anchor changed')
    s = s.replace(old, new, 1)

    old = ('\tret = bq2560x_charger_hw_init(info);\n'
           '\tif (ret) {\n'
           '\t\tdev_err(dev, "failed to bq2560x_charger_hw_init\\n");\n'
           '\t\tgoto err_psy_usb;\n'
           '\t}')
    new = ('\tret = bq2560x_charger_hw_init(info);\n'
           '\tif (ret) {\n'
           '\t\t/* yuanhang41: writes settle ~2min after reads on this unit;\n'
           '\t\t * async probe keeps this off the boot path while we wait. */\n'
           '\t\tint tries = 0;\n'
           '\t\twhile ((ret == -EIO || ret == -EREMOTEIO || ret == -ENXIO ||\n'
           '\t\t\tret == -ETIMEDOUT || ret == -EAGAIN) && tries < 24) {\n'
           '\t\t\tmsleep(15000);\n'
           '\t\t\tret = bq2560x_charger_hw_init(info);\n'
           '\t\t\ttries++;\n'
           '\t\t}\n'
           '\t\tif (ret) {\n'
           '\t\t\tdev_err(dev, "failed to bq2560x_charger_hw_init\\n");\n'
           '\t\t\tgoto err_psy_usb;\n'
           '\t\t}\n'
           '\t}')
    if s.count(old) != 1:
        raise ValueError('hw_init error anchor changed')
    s = s.replace(old, new, 1)

    if '#include <linux/delay.h>' not in s:
        s = s.replace('#include <linux/gpio/consumer.h>',
                      '#include <linux/delay.h>\n#include <linux/gpio/consumer.h>', 1)
    charger.write_text(s, encoding='utf-8')

    fgu = kernel / 'drivers' / 'power' / 'supply' / 'sprd_fuel_gauge_core.c'
    s = fgu.read_text(encoding='utf-8')

    old = ('\t.name\t\t\t= "sc27xx-fgu",\n'
           '\t.type\t\t\t= POWER_SUPPLY_TYPE_UNKNOWN,')
    new = ('\t.name\t\t\t= "sc27xx-fgu",\n'
           '\t.type\t\t\t= POWER_SUPPLY_TYPE_BATTERY,')
    if s.count(old) != 1:
        raise ValueError('fgu desc anchor changed')
    s = s.replace(old, new, 1)

    old = '\t\t\tval->intval = data->boot_cap;'
    if s.count(old) != 1:
        raise ValueError('fgu boot_cap anchor changed')
    s = s.replace(old, '\t\t\tval->intval = data->boot_cap / 10;', 1)

    old = '\t\tval->intval = sprd_fgu_capacity_remap(data, data->bat_soc);'
    if s.count(old) != 1:
        raise ValueError('fgu capacity anchor changed')
    new = ('\t\tval->intval = sprd_fgu_capacity_remap(data, data->bat_soc) / 10;\n'
           '\t\tbreak;\n'
           '\n'
           '\tcase POWER_SUPPLY_PROP_STATUS:\n'
           '\t\t/* Written by charger-manager (cm_set_charging_status). */\n'
           '\t\tval->intval = data->chg_sts;\n'
           '\t\tbreak;')
    s = s.replace(old, new, 1)

    old = 'sprd_fgu_props[] = {\n\tPOWER_SUPPLY_PROP_HEALTH,'
    if s.count(old) != 1:
        raise ValueError('fgu props anchor changed')
    s = s.replace(old, 'sprd_fgu_props[] = {\n\tPOWER_SUPPLY_PROP_STATUS,\n\tPOWER_SUPPLY_PROP_HEALTH,', 1)

    fgu.write_text(s, encoding='utf-8')
    print('charger-fgu staged: 0x6b gate + probe defer + fgu type/status/percent')


if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
