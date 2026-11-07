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
    if 'yuanhang41: this unit answers at the DT address' in s:
        return  # idempotent: staged in a previous pass

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

    # This silicon (SGM41511 family, REG_B=0x14 at 0x6b) has NO register
    # 0x0d: reads float to 0xff and writes NACK, which kills hw_init. The
    # 41S termination-current coding (for the 0x1a SGM41513) writes it;
    # restore the vendor REG03-only coding that this chip implements.
    old = ("""    u8 code, offset = 0;
    int ret = bq2560x_update_bits(info, 0x0d, BIT(0), cur > 240 ? 0 : BIT(0));
    if (ret) return ret;
    if (cur > 240) {
        if (cur <= 360) { offset = 5; code = (cur - 240) / 60; }
        else if (cur < 480) code = 7;
        else if (cur <= 1200) { offset = 8; code = (cur - 480) / 120; }
        else code = 15;
    } else {
        if (cur < 5) code = 0;
        else if (cur <= 20) code = (cur - 5) / 5;
        else if (cur <= 60) { offset = 3; code = (cur - 20) / 10; }
        else if (cur < 80) code = 7;
        else { offset = 8; code = (cur - 80) / 20; }
    }
    code = min_t(u8, code + offset, 15);
    return bq2560x_update_bits(info, BQ2560X_REG_3,
        BQ2560X_REG_TERMINAL_CUR_MASK, code);""")
    new = ("""    u8 reg_val;

    /* yuanhang41 silicon: REG 0x0d is not implemented - REG03 only. */
    if (cur <= 60)
        reg_val = 0x0;
    else if (cur >= 480)
        reg_val = 0x8;
    else
        reg_val = (cur - 60) / 60;

    return bq2560x_update_bits(info, BQ2560X_REG_3,
        BQ2560X_REG_TERMINAL_CUR_MASK, reg_val);""")
    if s.count(old) != 1:
        raise ValueError('41S termina_cur body anchor changed')
    s = s.replace(old, new, 1)
    charger.write_text(s, encoding='utf-8')

    fgu = kernel / 'drivers' / 'power' / 'supply' / 'sprd_fuel_gauge_core.c'
    s = fgu.read_text(encoding='utf-8')

    if 'POWER_SUPPLY_TYPE_BATTERY' in s.split('sc27xx-fgu')[1][:200]:
        print('charger-fgu staged: already applied in a previous pass')
        return  # idempotent: nothing resets the fgu file between passes

    old = ('\t.name\t\t\t= "sc27xx-fgu",\n'
           '\t.type\t\t\t= POWER_SUPPLY_TYPE_UNKNOWN,')
    new = ('\t.name\t\t\t= "sc27xx-fgu",\n'
           '\t.type\t\t\t= POWER_SUPPLY_TYPE_BATTERY,')
    if s.count(old) != 1:
        raise ValueError('fgu desc anchor changed')
    s = s.replace(old, new, 1)

    # Keep the vendor per-mille capacity scale: charger-manager expects it
    # and converts to percent for its "battery" psy (uisoc = cap / 10).
    old = '\t\tval->intval = sprd_fgu_capacity_remap(data, data->bat_soc);'
    if s.count(old) != 1:
        raise ValueError('fgu capacity anchor changed')
    new = ('\t\tval->intval = sprd_fgu_capacity_remap(data, data->bat_soc);\n'
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
    print('charger-fgu staged: 0x6b gate + fgu type/status; capacity stays per-mille for CM')


if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
