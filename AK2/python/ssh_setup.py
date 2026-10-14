"""
Setter opp SSH på en Cisco switch eller router via konsollkabel (seriell).

Krever: pip install pyserial
Kjør:   sudo python3 ssh_setup.py
"""

import time
from getpass import getpass  # skjuler passordet mens du skriver

import serial  # fra pakken pyserial


def send(tilkobling, kommando, vent=1):
    """Sender én kommando til enheten, venter litt, og skriver ut svaret."""
    tilkobling.write((kommando + "\r").encode())
    time.sleep(vent)
    svar = tilkobling.read(tilkobling.in_waiting).decode(errors="ignore")
    print(svar, end="")
    return svar


def vekk_enheten(tilkobling):
    """
    Trykker Enter til enheten viser en vanlig prompt (> eller #).
    Svarer automatisk på spørsmålene en ny/nullstilt enhet stiller ved første oppstart.
    """
    print("Venter på enheten (kan ta litt tid hvis den nettopp har startet)...\n")
    for _ in range(60):  # prøver i opptil ca. 2 minutter
        svar = send(tilkobling, "", 2).strip()

        if "initial configuration dialog" in svar:
            # "Would you like to enter the initial configuration dialog? [yes/no]"
            send(tilkobling, "no", 10)
        elif "terminate autoinstall" in svar:
            # "Would you like to terminate autoinstall? [yes]"
            send(tilkobling, "yes", 5)
        elif "(config" in svar:
            # Står fast i config-modus fra før – gå ut til vanlig modus
            send(tilkobling, "end")
        elif svar.endswith(">") or svar.endswith("#"):
            return  # vanlig prompt, enheten er klar

    print("\nFikk ikke kontakt med enheten. Sjekk kabel, port og at den er skrudd på.")
    raise SystemExit(1)


def finn_interfacer(tilkobling):
    """Kjører 'show ip interface brief' og returnerer en liste med interfaces."""
    svar = send(tilkobling, "show ip interface brief", 3)
    interfacer = []
    for linje in svar.splitlines():
        deler = linje.split()
        # Interface-linjer ser slik ut:
        # GigabitEthernet1/0/1  unassigned  YES unset  down  down
        # Kolonne 3 er alltid YES eller NO, så vi bruker det for å kjenne dem igjen
        if len(deler) >= 6 and deler[2] in ("YES", "NO"):
            navn = deler[0]
            status = deler[-2] + "/" + deler[-1]  # f.eks. up/up
            interfacer.append((navn, status))
    return interfacer


def velg_interface(interfacer):
    """Viser en nummerert liste og lar brukeren velge ett interface."""
    print("\n\nInterfaces på enheten:")
    print("  0. Skriv inn selv (f.eks. 'vlan 20' som ikke finnes ennå)")
    for nummer, (navn, status) in enumerate(interfacer, start=1):
        print(f"  {nummer}. {navn:<25} {status}")

    valg = ""
    while not (valg.isdigit() and 0 <= int(valg) <= len(interfacer)):
        valg = input(f"Velg interface for IP (0-{len(interfacer)}): ").strip()

    if valg == "0":
        return input("Skriv interface (f.eks. vlan 20): ").strip()
    return interfacer[int(valg) - 1][0]


def main():
    # ---------- 1. Hent input fra brukeren ----------
    print("=== SSH-oppsett for Cisco switch/router ===")
    # Velg port 1-6. COM3 tilsvarer /dev/ttyS3 på Linux osv.
    portnummer = ""
    while portnummer not in ("1", "2", "3", "4", "5", "6"):
        portnummer = input("Seriellport (1-6): ").strip()
    port = f"/dev/ttyS{portnummer}"

    # Åpne porten med en gang, så vi vet at den virker før du fyller inn resten.
    # Cisco-konsoll bruker nesten alltid 9600 baud, 8 databit, ingen paritet, 1 stoppbit
    try:
        tilkobling = serial.Serial(port, baudrate=9600, timeout=1)
    except serial.SerialException as feil:
        print(f"\nKlarte ikke å åpne {port}.")
        if "Permission denied" in str(feil):
            print("Porten er sannsynligvis i bruk av et annet program (PuTTY o.l.).")
            print("Lukk det, eller trekk ut og sett inn konsollkabelen igjen.")
            print("Husk også å kjøre med sudo, eller være med i gruppa 'dialout'.")
        else:
            print("Sjekk at kabelen står på riktig COM-nummer i Enhetsbehandling.")
        raise SystemExit(1)
    print(f"Porten {port} er åpen.\n")

    print("Hva slags enhet er det?")
    print("  1. Router")
    print("  2. L2 Switch")
    print("  3. L3 Switch")
    valg = ""
    while valg not in ("1", "2", "3"):
        valg = input("Velg enhet (1-3): ").strip()
    enhet = {"1": "router", "2": "l2", "3": "l3"}[valg]

    naavaerende_enable = getpass(
        "Nåværende enable-passord på enheten (ofte 'cisco' eller 'class', Enter hvis ingen): "
    )

    hostname = input("Hostname (f.eks. SW1): ")
    domene = input("Domenenavn (f.eks. lab.local): ")
    brukernavn = input("SSH-brukernavn: ")
    passord = getpass("SSH-passord: ")
    enable_passord = getpass("Enable secret (passord for privilegert modus): ")

    # ---------- 2. Koble til enheten ----------
    print(f"\nKobler til enheten på {port}...\n")

    vekk_enheten(tilkobling)

    # ---------- 3. Gå inn i privilegert modus ----------
    svar = send(tilkobling, "enable")
    if "Password" in svar:
        # Enheten har allerede et enable-passord (f.eks. cisco eller class)
        send(tilkobling, naavaerende_enable)

    send(tilkobling, "terminal length 0")  # ingen "--More--" i output

    # ---------- 4. Finn interfaces og la brukeren velge ----------
    interfacer = finn_interfacer(tilkobling)
    if interfacer:
        interface = velg_interface(interfacer)
    else:
        # Fant ingen (f.eks. rar output) – da skriver brukeren det selv
        interface = input("\nFant ingen interfaces. Skriv interface selv (f.eks. vlan 1): ")
    print(f"Valgt: {interface}")

    ip = input("IP-adresse: ")
    maske = input("Subnettmaske (f.eks. 255.255.255.0): ")
    gateway = input("Default gateway (trykk Enter for å hoppe over): ")

    # L2-switch med management på et annet VLAN enn 1 (f.eks. Vlan20):
    # VLAN-et må lages, og portene mot gatewayen må bære det, ellers når
    # Ansible aldri frem. Resten av portene tar Ansible seg av senere.
    mgmt_vlan = ""
    access_porter = []
    trunk_porter = []
    if enhet == "l2" and interface.lower().startswith("vlan"):
        mgmt_vlan = "".join(tegn for tegn in interface if tegn.isdigit())
        if mgmt_vlan != "1":
            print(f"\nManagement ligger i VLAN {mgmt_vlan}. Hvilke porter skal bære det?")
            access_porter = input(
                f"Access-porter i VLAN {mgmt_vlan}, kommaseparert (f.eks. fa0/1,fa0/2, Enter = ingen): "
            ).replace(" ", "").split(",")
            trunk_porter = input(
                "Trunk-porter, kommaseparert (f.eks. fa0/4, Enter = ingen): "
            ).replace(" ", "").split(",")
            # Fjern tomme verdier hvis brukeren bare trykket Enter
            access_porter = [p for p in access_porter if p]
            trunk_porter = [p for p in trunk_porter if p]

    # ---------- 5. Konfigurasjon ----------
    kommandoer = [
        "configure terminal",
        f"hostname {hostname}",
        "no ip domain-lookup",
        f"ip domain-name {domene}",
        f"enable secret {enable_passord}",
        f"username {brukernavn} privilege 15 secret {passord}",
    ]

    # Lag management-VLAN og sett opp portene som skal bære det (kun L2-switch)
    if mgmt_vlan and mgmt_vlan != "1":
        kommandoer += [f"vlan {mgmt_vlan}", "exit"]
        for p in access_porter:
            kommandoer += [f"interface {p}", "switchport mode access",
                           f"switchport access vlan {mgmt_vlan}", "no shutdown", "exit"]
        for p in trunk_porter:
            kommandoer += [f"interface {p}", "switchport mode trunk", "no shutdown", "exit"]

    kommandoer.append(f"interface {interface}")

    # L3-switch: fysiske porter må gjøres om til rutede porter før de kan få IP.
    # Vlan- og Loopback-interfaces har ikke switchport, så der hopper vi over det.
    if enhet == "l3" and not interface.lower().startswith(("vlan", "loopback")):
        kommandoer.append("no switchport")

    kommandoer += [
        f"ip address {ip} {maske}",
        "no shutdown",
        "exit",
    ]

    if gateway:
        if enhet == "l2":
            kommandoer.append(f"ip default-gateway {gateway}")
        else:
            kommandoer.append(f"ip route 0.0.0.0 0.0.0.0 {gateway}")

    # Nyere IOS-XE (f.eks. ISR 4221) bruker mellomrom i stedet for bindestrek
    # i noen kommandoer. Feiler den gamle skrivemåten, prøver vi den nye.
    alternativer = {
        "no ip domain-lookup": "no ip domain lookup",
        f"ip domain-name {domene}": f"ip domain name {domene}",
    }

    # Hvis et interface ikke finnes, hopper vi over alle kommandoene under det
    # frem til "exit". Ellers ville "exit" tatt oss ut av config-modus, og
    # resten av kommandoene ville havnet i feil modus.
    hopp_over = False
    ukjente_interfacer = []
    for kommando in kommandoer:
        if hopp_over:
            if kommando == "exit":
                hopp_over = False
            continue

        svar = send(tilkobling, kommando)
        if "Invalid input" in svar:
            if kommando in alternativer:
                send(tilkobling, alternativer[kommando])
            elif kommando.startswith("interface "):
                navn = kommando[len("interface "):]
                print(f"\n!!! Fant ikke {navn} på enheten – hopper over det.\n")
                ukjente_interfacer.append(navn)
                hopp_over = True

    # RSA-nøkler trengs for SSH. Dette tar litt tid, så vi venter lenger.
    svar = send(tilkobling, "crypto key generate rsa modulus 2048", 15)
    if "[yes/no]" in svar:  # noen enheter spør om vi vil erstatte gamle nøkler
        send(tilkobling, "yes", 15)

    # Switcher (L2 og L3) har VTY-linjer 0-15, de fleste routere 0-4
    vty = "0 4" if enhet == "router" else "0 15"

    # Enhetene er gamle: tillat eldre krypteringsalgoritmer så nyere PC-er får koblet til
    send(tilkobling, "ip ssh server algorithm encryption "
                     "aes128-cbc 3des-cbc aes192-cbc aes256-cbc")

    for kommando in [
        "ip ssh version 2",
        f"line vty {vty}",
        "login local",
        "transport input ssh",
        "exit",
        "end",
    ]:
        send(tilkobling, kommando)

    # ---------- 6. Lagre ----------
    send(tilkobling, "write memory", 5)

    tilkobling.close()

    if ukjente_interfacer:
        print("\n\nOBS! Disse interfacene fantes ikke og ble hoppet over:")
        for navn in ukjente_interfacer:
            print(f"  - {navn}")
        print("Sjekk portnavnene med 'show ip interface brief' og kjør scriptet på nytt.")
    print("\n\nFerdig! Test med:")
    print(f"  Fra PC:              ssh -c aes128-cbc {brukernavn}@{ip}")
    print(f"  Fra en annen switch: ssh -l {brukernavn} -c aes128-cbc {ip}")


if __name__ == "__main__":
    main()
