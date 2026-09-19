# ADR 0023 — Read-only media inventory and exact duplicates

Status: aceita. Entrega: Milestone 5A.

`dee media inventory` inspeciona exclusivamente EvidenceFile e ArchiveMember da
Foundation, num snapshot de catálogo via read_catalog. Schema permanece v5, sem
migration, backup, entidade MediaAsset/MediaHash, run, view, índice ou cache.
Nenhum arquivo de resultado é escrito pelo comando. JSON determinístico vai a stdout.

EvidenceFiles são encontrados pela descoberta segura de originals; membros usam
working_relative_path catalogado, com validação de confinamento e links. O container
original também é verificado. Não há extração, reparação ou rematerialização.
Arquivos não catalogados não entram. Ausência ou divergência falha a consulta inteira
com erro técnico/exit 2, sem JSON parcial e sem reescrever baseline.

Reutiliza original_reader (abertura read-only e fingerprint antes/depois) e
sha256_stream da Foundation. Lê prefixo de até 4096 bytes, retorna ao início e
compara tamanho/hash streaming com o catálogo no mesmo handle. Verifica **todas**
as ocorrências, inclusive unknown: mudança de assinatura não pode ocultar uma
mídia alterada. Não cria um segundo conceito de hash exato. O snapshot SQLite não
torna todo o filesystem atômico; estabilidade é conferida por leitura de arquivo.

Assinaturas suportadas: JPEG, PNG, GIF87a/89a e RIFF/WEBP. ISO-BMFF aceita ftyp
completo dentro do prefixo, tamanhos normais/estendidos, payload mínimo e brands
alinhadas; permite até 16 boxes iniciais free/skip/wide. Tamanho zero, truncamento,
box fora do limite ou estrutura inválida produz unknown. Brands major/compatíveis
explícitas avif/avis → avif; heic/heix/hevc/hevx → heic; mif1/msf1 → heif, com
preferência pela família de codec explícita. Famílias conflitantes ou major não
suportada → iso-bmff sem media_kind. MP4/MOV genéricos não provam presença de vídeo
e ficam fora dos media items. Unknown é preferível à inferência por extensão.

Referências técnicas: [MP4 Registration Authority — brands](https://mp4ra.org/registered-types/brands)
e [WebP container specification](https://developers.google.com/speed/webp/docs/riff_container).
O reconhecimento é de assinatura, não valida decodificação ou integridade semântica
do bitstream. extension_hint é apenas metadata; mismatch não afirma adulteração.

Items preservam source_kind, IDs, paths relativos de original/member, size_bytes,
cataloged_sha256, media_kind/format e extension_hint; nunca path físico extraído ou
absoluto. Ordenação: source_kind, evidence_relative_path, member_path (null como vazio),
IDs como desempate. verified_media só inclui reconhecidos após verificação bem-sucedida.
recognized_media + unrecognized_occurrences = scanned_occurrences.

Agrupamento read-only por SHA-256 catalogado somente entre mídias verificadas, count
>= 2. Cada grupo contém sha256, occurrence_count e todas as occurrences com suas
proveniências. N ocorrências geram um grupo, não N² pares. Grupos ordenam count DESC,
SHA ASC; ocorrências preservam a ordem dos items. Hash igual não elimina fontes nem
prova mesmo evento, upload, autor ou aquisição.

Sem perceptual hash, Pillow, imagehash, ffmpeg, decode, thumbnail, EXIF ou OCR.
Originais não são alterados. Leituras podem atualizar atime conforme o mount/filesystem;
não há promessa de preservação de atime fora de ambiente que a garanta. Outputs reais,
incluindo paths/hashes, continuam fora do Git.
