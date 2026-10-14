# Del 1 – SSH-oppsett med Python via konsollkabel

`ssh_setup.py` tar en Cisco-enhet fra å bare kunne nås med konsollkabel til å være tilgjengelig over SSH. Scriptet setter bare opp det minste som trengs for at Ansible skal komme inn, resten tar Ansible seg av.

Scriptet fungerer på router, L2-switch og L3-switch, i tillegg til å fungere på både eldre IOS og nyere IOS-XE. Ingenting er hardkodet, så port, navn, brukere, passord og IP skrives inn når scriptet kjøres.

## Installasjon (én gang)

Installer i bash:
```bash
sudo apt install python3 python3-serial openssh-client
```

- **`python3`** kjører scriptet. Det finnes som regel allerede i WSL/Ubuntu.
- **`python3-serial`** (pyserial) gjør at Python kan snakke med konsollkabeler, det er dette som er `import serial` i scriptet.
- **`openssh-client`** gir `ssh`-kommandoen, som brukes for å teste at SSH virker etterpå. Finnes som regel også allerede.

For å sjekke at det virker:

```bash
python3 -c "import serial; print('pyserial OK')"
```

## Hva scriptet setter opp

- Kommer seg forbi oppstartsspørsmålene på nye eller nullstilte enheter ("initial configuration dialog" osv.)
- Hostname, domenenavn og `no ip domain-lookup`
- `enable secret` og en lokal bruker med `privilege 15`
- IP på ett interface (management) med `no shutdown`, og eventuelt en default gateway
- RSA-nøkler (2048 bit), SSH versjon 2, og eldre krypteringstyper sånn at nye PC-er får koblet til
- VTY-linjene, med kun SSH og innlogging med lokal bruker (0–4 på router, 0–15 på switch)
- Lagrer til slutt med `write memory`

### Spesialtilfeller scriptet håndterer

- **L3-switch med fysisk port:** sender `no switchport` før IP-en settes.
- **L2-switch med management i et annet VLAN enn 1:** lager VLAN-et og spør hvilke porter som skal være access eller trunk for det.
- **Nyere IOS-XE (f.eks. ISR 4221):** prøver `ip domain name` hvis `ip domain-name` blir avvist.
- **Interface som ikke finnes:** hopper over det i stedet for å havne i feil modus, og lister det opp til slutt.

## Forutsetninger

- Pakkene over er installert.
- Konsollkabel fra PC-en til enheten.
- Du vet COM-nummeret til kabelen (Windows: Enhetsbehandling → Porter).
- Du har tilgang til seriellporten. 
- Brukertilganger til å kjøre med `sudo`.
- PuTTY og andre terminalprogrammer må være **lukket**, siden bare ett program kan bruke porten om gangen.

## Kjøring

```bash
cd AK2/python
sudo python3 ssh_setup.py
```

Scriptet spør om dette i rekkefølge: seriellport, enhetstype, nåværende enable-passord, hostname, domenenavn, SSH-bruker og SSH-passord, og ny enable secret.

Så kobler det til, viser interfacene på enheten og lar deg velge ett. Valg `0` betyr at du skriver det inn selv, for eksempel `vlan 20` som ikke finnes ennå. Til slutt spør det om IP, maske og gateway.

Default Gateway er viktig å sette opp på distribution routerne dersom de trenger et utgangspunkt for at SSH-en skal kunne routes videre under neste steg (ansible), mer om dette står under *Hvorfor gateway trengs*.

### Eksempel svar for STUD2

**ST2-C-SW1**
- Type: `3. L3 Switch`
- Interface: `Gi1/0/1`
- IP / maske: `10.2.99.1` / `255.255.255.252`
- Gateway: ingen (trykk Enter)

**ST2-D-RO1**
- Type: `1. Router`
- Interface: `Gi0/0/0`
- IP / maske: `10.2.0.2` / `255.255.255.252`
- Gateway: `10.2.0.1`

**ST2-D-RO2**
- Type: `1. Router`
- Interface: `Gi0/0`
- IP / maske: `10.2.0.6` / `255.255.255.252`
- Gateway: `10.2.0.5`

**ST2-A-SW1**
- Type: `2. L2 Switch`
- Interface: `0`, og skriv `vlan 20`
- IP / maske: `10.2.20.11` / `255.255.255.0`
- Gateway: `10.2.20.1`
- Access-porter i VLAN 20: `fa0/1,fa0/2`
- Trunk-porter: `fa0/3`

**ST2-A-SW2**
- Type: `2. L2 Switch`
- Interface: `0`, og skriv `vlan 20`
- IP / maske: `10.2.20.12` / `255.255.255.0`
- Gateway: `10.2.20.1`
- Access-porter i VLAN 20: ingen (trykk Enter)
- Trunk-porter: `gi1/0/1`

### Hvorfor gateway trengs

Management-PC-en er bare koblet til core. Routerne og access-switchene ligger i andre nett, og må derfor vite hvor svarene til PC-en skal sendes. Det må de vite før Ansible har satt opp OSPF, og derfor får de en default gateway her. Core trenger ingen, siden den er direkte koblet til PC-en.

## Test etterpå

```bash
ping 10.2.99.1
ssh cisco@10.2.99.1
```

Eldre enheter (f.eks. 2901) bruker gamle algoritmer som nyere SSH-klienter har skrudd av. Da kan du enten bruke den lange kommandoen:

```bash
ssh -o KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    -c aes128-cbc cisco@10.2.0.2
```

eller legge dette i `~/.ssh/config` én gang:

```
Host 10.2.*
    KexAlgorithms +diffie-hellman-group14-sha1,diffie-hellman-group1-sha1
    HostKeyAlgorithms +ssh-rsa
    PubkeyAcceptedAlgorithms +ssh-rsa
    Ciphers +aes128-cbc
```

## Feilsøking

| Feil | Løsning |
|------|---------|
| `Permission denied: /dev/ttySX` | Glemt `sudo`, eller PuTTY har porten åpen. Lukk den, eller trekk ut og sett inn kabelen igjen. |
| `Input/output error` på porten | Feil COM-nummer, sjekk Enhetsbehandling. |
| `% Invalid input` på et interface | Portnavnet finnes ikke på enheten. Sjekk med `show ip interface brief`. |
| `% Please define a domain-name first` | Domenenavnet ble ikke satt (gammel versjon av scriptet på IOS-XE). Kjør på nytt. |
| Enheten svarer ikke | Den starter kanskje fortsatt opp, scriptet venter i ca. 2 minutter. Sjekk kabel og strøm. |
