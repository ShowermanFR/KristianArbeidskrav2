# AK2 – Automatisering av Cisco-nettverk (STUD2)

I dette repoet settes STUD2-siden av AK2-nettverket opp automatisk. Det gjøres i to steg, og de må tas i denne rekkefølgen:

1. **Python** (python/README_python.md)
   Scriptet kobler seg til hver enhet individuelt med konsollkabel og gjør den klar for SSH. Uten SSH kommer ikke Ansible inn på enhetene.
2. **Ansible** (README_ansible.md)
   Ansible kobler seg til over SSH og setter opp resten, altså routing, OSPF, HSRP, DHCP, VLAN-er, trunker og EtherChannel.

## Topologi (STUD2)

```
            MGMT-PC (10.2.99.2)
                 │ Gi1/0/1
           ┌─────┴─────┐
           │ ST2-C-SW1 │  Core L3-switch
           └──┬─────┬──┘
       Gi1/0/2│     │Gi1/0/3        (rutede /30-linker, OSPF area 0)
     ┌────────┴┐   ┌┴────────┐
     │ST2-D-RO1│   │ST2-D-RO2│      Distribution: HSRP + DHCP for VLAN 20
     └────┬────┘   └────┬────┘
   Gi0/0/1│             │Gi0/1      (access-porter i VLAN 20)
       Fa0/1┌───────────┐Fa0/2
            │ ST2-A-SW1 │           Access
            └─────┬─────┘
             Fa0/3│ trunk (VLAN 10,20)
            Gi1/0/1┌───────────┐
                   │ ST2-A-SW2 │════ EtherChannel (Gi1/0/2-3, LACP) ════ STUD1
                   └─┬───────┬─┘
             Gi1/0/11│       │Gi1/0/12
               PC-VLAN20   PC-VLAN10
```
(Topologi er AI-generert basert på arbeidskravet medfølgende topologi + egen IP/Port-plan. Porter og VLAN kan være slik man vil selv, men da må resten av README filene følges opp med samme konfigurasjon)

## Enheter

| Enhet     | Rolle                                |
|-----------|--------------------------------------|
| ST2-C-SW1 | Core L3-switch (C3650)               |
| ST2-D-RO1 | Dist. Router (ISR 4221), HSRP Active |
| ST2-D-RO2 | Dist. Router (2901), HSRP Standby    |
| ST2-A-SW1 | Access-switch (C2960)                |
| ST2-A-SW2 | Access-switch (C1000)                |

Hele IP-planen ligger i `STUD1_STUD2_fullstendig_IP_plan.xlsx`.

## Avtalt med STUD1

- VLAN 10 er STUD1 sitt og VLAN 20 er vårt (STUD2). Begge går over trunkene og EtherChannel.
- EtherChannel mellom ST2-A-SW2 og access-switchen til STUD1 er satt opp som trunk, med LACP `active` på begge sider.
- Routerne til STUD1 deler ut DHCP og er gateway for VLAN 10.
