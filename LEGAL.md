# Legal notice and interoperability statement

This document explains why this project exists, what it does and does not do, and the European legal framework it
relies on. It is **not legal advice**. If you plan to use this library commercially or at scale, consult a lawyer
qualified in your jurisdiction.

## 1. Independence

`evdc-network-api` is an independent, non-commercial, open-source project. It is not affiliated with, endorsed by, or
supported by EVDC or its developers. "EVDC" and related names are used only to identify the service this library
interoperates with (nominative use).

## 2. Intent

The sole purpose of this project is **interoperability**: allowing an EVDC user to retrieve **their own** charging
session data (time, energy, cost) and use it in an independently created program, such as software that tracks the
charging of an electric vehicle and needs the cost of each public charging session.

The project does **not** aim to:

- reproduce, replace or compete with the EVDC app or any of its functions;
- copy or redistribute EVDC source code, binaries, graphics, keys or certificates;
- access data belonging to other users, or network-wide data in bulk;
- bypass payment, authentication, tariffs, rate limits or technical protection measures.

## 3. Method

The interface is documented by:

1. using the official EVDC app with the author's own, lawfully held account;
2. observing the network traffic between the app and its backend while using it normally;
3. where strictly necessary, studying the app to understand the format of the data exchanged with the server.

Only the information indispensable to interoperate — endpoints, request and response formats, authentication flow —
is recorded in this repository. No part of the original program's code is included.

## 4. European legal framework

### 4.1 Computer Programs Directive — Directive 2009/24/EC

[Directive 2009/24/EC](https://eur-lex.europa.eu/eli/dir/2009/24/oj) on the legal protection of computer programs is
the main reference for analysing software to achieve interoperability.

- **Article 1(2)** — Ideas and principles underlying any element of a program, *including those which underlie its
  interfaces*, are not protected by copyright. Only the expression of the program is.
- **Article 5(3)** — A person entitled to use a copy of a program may, without the rightholder's authorisation,
  *observe, study or test* its functioning to determine the ideas and principles underlying it, while loading,
  displaying, running, transmitting or storing the program. This is the basis for the traffic-observation method
  described above.
- **Article 6 — Decompilation** — Reproduction of the code and translation of its form are allowed without
  authorisation when indispensable to obtain the information necessary to achieve the interoperability of an
  *independently created program* with other programs, provided that:
  - (a) the acts are performed by a licensee or another person entitled to use a copy of the program;
  - (b) the information necessary for interoperability has not previously been readily available;
  - (c) the acts are confined to the parts of the original program necessary for interoperability.

  Under **Article 6(2)** the information obtained may not be used for goals other than interoperability, given to
  others except when necessary for interoperability, or used to develop a program substantially similar in its
  expression. This project is designed to stay within these limits (see sections 2 and 3).
- **Article 8** — Contractual provisions contrary to Article 6 or to the exceptions in Article 5(2) and 5(3) are
  *null and void*.
- **Recitals 10 and 15** — explain that interoperability (the ability to exchange information and mutually use the
  information exchanged) is a legitimate objective, and that decompilation to achieve it is allowed in the limited
  circumstances above.

National implementation in Italy: **Law no. 633 of 22 April 1941** (Copyright Law), articles **64-ter(3)** and
**64-quater**, transpose Articles 5(3) and 6 of the Directive.

Relevant case law of the Court of Justice of the EU:

- [**C-406/10, SAS Institute**](https://curia.europa.eu/juris/liste.jsf?num=C-406/10) (2 May 2012) — the
  functionality of a program, its programming language and data file formats are not protected as such; a licensee
  may observe, study and test the program to determine its underlying ideas and principles, and this cannot be
  excluded by contract.
- [**C-13/20, Top System**](https://curia.europa.eu/juris/liste.jsf?num=C-13/20) (6 October 2021) — clarifies the
  scope of decompilation under the Directive and confirms that a lawful acquirer may decompile a program where this is
  necessary to use it in accordance with its intended purpose, including error correction (Article 5(1)).

### 4.2 Trade Secrets Directive — Directive (EU) 2016/943

[Directive (EU) 2016/943](https://eur-lex.europa.eu/eli/dir/2016/943/oj), **Article 3(1)(b)**, states that the
acquisition of a trade secret is lawful when obtained by observation, study, disassembly or testing of a product or
object that has been made available to the public or that is lawfully in the possession of the acquirer, who is free
from any legally valid duty to limit the acquisition. **Recital 16** confirms that reverse engineering of a lawfully
acquired product should be considered a lawful means of acquiring information, except when otherwise contractually
agreed. In Italy it is transposed by Legislative Decree no. 63 of 11 May 2018 (amending art. 98–99 of the Industrial
Property Code).

### 4.3 Data portability — GDPR, Regulation (EU) 2016/679

Charging sessions linked to an account (time, place, energy, amount paid) are personal data of the account holder.
Under the [GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj), **Article 15** (right of access) and **Article 20**
(right to data portability) give the data subject the right to obtain their personal data and to receive it in a
structured, commonly used and machine-readable format in order to transmit it to another controller. This library
helps a user exercise, for their own data, the purpose these rights pursue. It does not replace a formal request to
the controller.

### 4.4 Data Act — Regulation (EU) 2023/2854

The [Data Act](https://eur-lex.europa.eu/eli/reg/2023/2854/oj), applicable since **12 September 2025**, strengthens
the right of users of connected products and *related services* to access the data generated by their use
(**Articles 3–5**) and to share it with third parties of their choice. Charging data is generated by the user's use of
connected charging equipment and services. The Data Act also states (**Article 4(4)**) that data holders must not make
the exercise of these rights unduly difficult, and it reflects the general European policy goal of reducing lock-in.

### 4.5 Alternative Fuels Infrastructure Regulation — Regulation (EU) 2023/1804

[AFIR](https://eur-lex.europa.eu/eli/reg/2023/1804/oj), **Article 5**, requires operators of publicly accessible
charging points to display prices transparently and in a clear, non-discriminatory way. Price transparency for the
end user is therefore an explicit goal of EU law for charging infrastructure; making the user's own paid prices
available to the tools they use is consistent with it.

## 5. Responsible use

Users of this library must:

- use it only with their own EVDC account and their own data;
- comply with applicable laws, including data protection law when processing data;
- avoid excessive request rates that could burden the EVDC service;
- not use it to circumvent payments, tariffs or technical protection measures.

The authors accept no liability for misuse. If you are a rightholder and believe something in this repository goes
beyond what is needed for interoperability, please open an issue or contact the maintainer: it will be reviewed and,
where appropriate, removed promptly.

## 6. References

| Act | Provisions | Link |
|---|---|---|
| Directive 2009/24/EC (Computer Programs) | Art. 1(2), 5(3), 6, 8; recitals 10, 15 | [EUR-Lex](https://eur-lex.europa.eu/eli/dir/2009/24/oj) |
| Directive (EU) 2016/943 (Trade Secrets) | Art. 3(1)(b); recital 16 | [EUR-Lex](https://eur-lex.europa.eu/eli/dir/2016/943/oj) |
| Regulation (EU) 2016/679 (GDPR) | Art. 15, 20 | [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj) |
| Regulation (EU) 2023/2854 (Data Act) | Art. 3–5 | [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2023/2854/oj) |
| Regulation (EU) 2023/1804 (AFIR) | Art. 5 | [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2023/1804/oj) |
| Italian Law 633/1941 (Copyright) | Art. 64-ter(3), 64-quater | [Normattiva](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1941-04-22;633) |
| CJEU C-406/10 *SAS Institute* | — | [Curia](https://curia.europa.eu/juris/liste.jsf?num=C-406/10) |
| CJEU C-13/20 *Top System* | — | [Curia](https://curia.europa.eu/juris/liste.jsf?num=C-13/20) |
