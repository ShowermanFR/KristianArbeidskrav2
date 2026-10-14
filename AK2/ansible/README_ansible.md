# Del 2 – Konfigurasjon med Ansible

Når alle enhetene har SSH (se ../python/README.md), setter Ansible opp resten av STUD2-nettverket. Oppsettet er delt i tre lag:

| Lag          | Enheter              | Hva settes opp                                             |
|--------------|----------------------|------------------------------------------------------------|
| Core         | ST2-C-SW1            | `ip routing`, rutede porter mot routerne, OSPF             |
| Distribution | ST2-D-RO1, ST2-D-RO2 | LAN-port i VLAN 20, HSRP (felles gateway `10.2.20.1`),     |
|              |                      | delt DHCP-scope, OSPF                                      |
| Access       | ST2-A-SW1, ST2-A-SW2 | VLAN 10/20, access-porter, trunker, EtherChannel mot STUD1 |

## Installasjon (én gang)

```bash
sudo apt install ansible python3-paramiko
ansible-galaxy collection install cisco.ios
```

- **`ansible`** er selve verktøyet.
- **`python3-paramiko`** er SSH-biblioteket Ansible bruker mot enhetene. Det er valgt i `group_vars/all. yml` (`ansible_network_cli_ssh_type: paramiko`) fordi det fortsatt støtter de gamle krypteringstypene på eldre Cisco-utstyr. Mangler det, får du feilen `paramiko is not installed`.
- **`cisco.ios`** er modulene som gjør at Ansible kan snakke med Cisco IOS (`ios_config`, `ios_vlans` osv.).

## Forutsetninger på management-PC-en

(Dersom det er satt opp IP-er og porter utenfor README_python.md, sett opp forutsetninger med egne IP-adresser og porter)
- Kabel fra PC-en til `Gi1/0/1` på ST2-C-SW1.
- Statisk IP på Ethernet-kortet: `10.2.99.2`, maske `255.255.255.252` og gateway `10.2.99.1`.
- Hvis PC-en **også** er koblet til et annet nett (f.eks. skolenettet), sender Windows trafikken til `10.2.x.x` feil vei. Da kan du enten:
  - legge til en rute (Ledetekst/CMD som administrator):
    ```
    route -p add 10.2.0.0 mask 255.255.0.0 10.2.99.1
    ```
  - eller deaktivere de andre nettverkskortene mens du jobber.

  Sjekk med `tracert -d 10.2.0.2`. Første hopp skal være `10.2.99.1`.

## Mappestruktur

```
ansible/
├── ansible.cfg            ← innstillinger (hvilken inventory, timeouts osv.)
├── inventory.ini          ← hvilke enheter som finnes, IP-ene deres og hvilken gruppe de er i
├── group_vars/all.yml     ← felles for alle: tilkobling, bruker, banner, VLAN-er, OSPF-prosess
├── host_vars/<enhet>.yml  ← det som er unikt per enhet: porter, IP-er, HSRP, DHCP, OSPF
├── templates/             ← Jinja2-maler, én per lag: core.j2, distribution.j2, access.j2
├── playbooks/             ← core.yml, distribution.yml, access.yml (én per lag)
│   └── verktoy/           ← test_ssh.yml, verifiser.yml, backup.yml
├── generert/              ← ferdige configer laget fra malene (kan leses før de sendes)
├── backup/                ← running-config hentet fra enhetene
└── site.yml               ← kjører alle lagene i riktig rekkefølge
```

## Kjøring

Alle kommandoer kjøres fra `ansible`-mappa. `-k` betyr at Ansible spør om SSH-passordet.

**1. Se configen uten å koble til noe** (krever verken passord eller nettverk):
```bash
ansible-playbook site.yml --tags generer
cat generert/ST2-C-SW1.cfg
```

**2. Test at Ansible kommer inn:**
```bash
ansible-playbook playbooks/verktoy/test_ssh.yml -k --limit ST2-C-SW1
```

**3. Kjør lag for lag, i denne rekkefølgen:**
```bash
ansible-playbook playbooks/core.yml -k --check --diff     # vis hva som vil endres
ansible-playbook playbooks/core.yml -k                    # gjør endringene

ansible-playbook playbooks/distribution.yml -k --check --diff
ansible-playbook playbooks/distribution.yml -k

ansible-playbook playbooks/access.yml -k --check --diff
ansible-playbook playbooks/access.yml -k
```

Rekkefølgen er viktig. Routerne kan først nås når core ruter, og access-switchene kan først nås når HSRP-gatewayen på routerne finnes.

`--limit <enhet>` kjører bare mot én enhet, f.eks. `--limit ST2-D-RO1`. Den kan bare ta inn innenfor gruppen til playbooken, så en access-switch med `distribution.yml` gir "no hosts matched".

**4. Alt på én gang** (når alt er satt opp første gang):
```bash
ansible-playbook site.yml -k --check --diff
ansible-playbook site.yml -k
```

Kjøres en playbook to ganger, skal andre gang gi `changed=0`. Da stemmer enhetene nøyaktig med var-filene.

## Verifisering og backup

(Verifisering og back-up script er AI-generert som en enkel metode for å teste oppsett etter kjøring) 
```bash
ansible-playbook playbooks/verktoy/verifiser.yml -k   # show-kommandoer på alle enheter
ansible-playbook playbooks/verktoy/backup.yml -k      # running-config til backup/
```

For å se hele den nye configen hos alle enheter kan man bruke Putty eller SSH for å se running-config med denne kommandoen.
`show run`

Ellers kan man bruke disse kommandoene for å se oversiklige lister over individuelle deler av configen:

| Kommando                    | Enhet     | Forventet resultat                                        |
|-----------------------------|-----------|-----------------------------------------------------------|
| `show ip ospf neighbor`     | Core      | To naboer, `2.2.2.2` og `2.2.2.3`, i tilstand FULL        |
| `show standby brief`        | Routere   | RO1 Active (pri 110), RO2 Standby, Virtual IP `10.2.20.1` |
| `show ip dhcp binding`      | Routere   | Klient-PC-en har en adresse i `10.2.20.100–199`           |
| `show etherchannel summary` | ST2-A-SW2 | Po1 merket (SU), medlemsportene merket (P)                |
| `show interfaces trunk`     | Access    | Trunkene tillater VLAN 10,20                              |

### Hvordan det henger sammen

**Data og logikk er skilt.** Alle IP-er, porter og VLAN-er står i `host_vars` og `group_vars`. Malene i `templates/` ser nesten ut som vanlig Cisco-config, bare med variabler der verdiene skal inn:

```jinja
{% for port in rutede_porter %}
interface {{ port.navn }}
 description {{ port.beskrivelse }}
 ip address {{ port.ip }} {{ port.maske }}
{% endfor %}
```

Når en playbook kjører, skjer dette:

1. Malen fylles ut med variablene til enheten og lagres som `generert/<enhet>.cfg`.
2. Den ferdige filen sendes til enheten med `ios_config`. Ansible sammenligner den med running-config og sender bare linjene som mangler.
3. Portene skrus på med `ios_interfaces`. `no shutdown` vises ikke i running-config, så hvis det sto i malen ville det gitt "changed" hver gang.
4. Configen lagres med `write memory`, men bare hvis noe faktisk ble endret.

Grunnen til at den genererte filen sendes i stedet for malen er at nyere Ansible (2.19+) av sikkerhetshensyn ikke fyller inn `{{ }}` i en fil som `ios_config` leser selv.

**Management-interfacet røres aldri.** Det står i `host_vars` som `mgmt_interface`, men bare som dokumentasjon. Core- og distribution-playbookene stopper med en feilmelding hvis noen legger det inn i `rutede_porter` ved en feil, ellers ville Ansible kuttet sin egen tilkobling.