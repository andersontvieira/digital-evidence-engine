# ADR 0027 — Platform file identity and read stability

Status: aceita. Correção W1 da Foundation; comportamento funcional da 5B preservado.

## Diagnóstico e causa

O fingerprint anterior comparava dev, ino, size, mtime_ns e ctime_ns indistintamente
entre path e handle, e antes/depois da leitura. No Windows Python 3.12 validado,
o diagnóstico controlado encontrou divergência path-stat/fstat somente em ctime_ns,
com identidade, tipo, tamanho, mtime, birthtime e atributos coerentes e estáveis.
SHA-256/tamanho continuavam iguais aos catalogados. Valores reais ficam apenas
no caso; o diagnóstico local emite contagens por campo, sem IDs/paths/timestamps.

Python 3.12 documenta st_ctime/st_ctime_ns como deprecated no Windows, com semântica
de criação em transição; não são invariantes portáveis de alteração de metadata.
st_birthtime é criação, não alteração. A causa confirmada do falso positivo é a
exigência de igualdade do ctime não-portável entre as duas APIs. Não se atribui uma
causa interna específica ao runtime além da divergência observada.
Referências: [os.stat_result](https://docs.python.org/3.12/library/os.html#os.stat_result)
e [mudanças no Python 3.12](https://docs.python.org/3.12/whatsnew/3.12.html).

## Política implementada

| Conceito | POSIX | Windows |
|---|---|---|
| Identidade do objeto | st_dev, st_ino, S_IFMT(st_mode) | st_dev, st_ino, S_IFMT(st_mode) |
| Estabilidade de leitura | st_size, st_mtime_ns, st_ctime_ns | st_size, st_mtime_ns |
| Creation time | Não exigido | st_birthtime não usado |

file_identity e read_stability tornam os conceitos explícitos. A seleção de
plataforma é interna, sem flag CLI para relaxar proteção. Birthtime é dispensável
para identificar objeto ou detectar mutação e sua exclusão evita novo acoplamento
não-portável; disponibilidade em POSIX não é exigida. Atime também não é invariante.

original_reader compara identidade **e** estabilidade do path validado com o handle
aberto, guarda o estado inicial desse handle e compara-o ao handle pós-leitura.
Também repete check_path e compara o path final com o inicial. Substituir o path
não pode transformar outro objeto em fonte aceita. Divergência de dispositivo,
inode, tipo, tamanho ou mtime continua falhando; POSIX mantém ainda ctime.
Não foi removido nenhum campo que protegia o comportamento POSIX anterior.

Políticas de links, hard links, junctions, reparse/path safety, confinamento e flags
de abertura read-only permanecem intactas. Nenhuma alteração de schema, hashes,
dependências, permissões ou metadata dos originais. SHA-256 streaming e tamanho
catalogados permanecem baselines obrigatórias nos serviços que verificam conteúdo;
o reader não substitui verificação de conteúdo por metadata.

## Cobertura e limites

Testes sintéticos exercitam ambas as políticas, ctime POSIX, ctime Windows
divergente, identidade/tipo, size/mtime, substituição entre validação/abertura e
troca/remoção do path final. Integração verifica SHA divergente inclusive com mesmo
tamanho, arquivo ausente, materialização e representatives. Quando Windows impede
remover arquivo aberto, simular a substituição no stat final verifica a comparação
sem depender do sharing mode. Testes existentes de segurança de paths são mantidos.

A primitive atende ingestão, verificação, leitura de parsers e mídia através do
reader/hash já compartilhado; esses serviços não foram reimplementados. As leituras
continuam sujeitas a limites de snapshot por arquivo: não há promessa de snapshot
atômico global ou de detectar toda alteração adversarial com metadata restaurada.
SHA-256/tamanho continuam necessários; ctime/creation time não os substituem.
Não prometer preservação de atime além da garantia do filesystem/mount.

A validação real Windows/Linux da 5B foi concluída e registrada em suplemento externo,
com igualdade de conteúdo, status, dimensões, pHash, representatives, occurrences,
política e bytes JSON, além de DB/filesystem e verify finais. O relatório anterior
da 5B e a ADR 0026 permanecem históricos, sem sobrescrita. Nenhum algoritmo
perceptual, threshold ou matriz de distância é acrescentado por W1.
