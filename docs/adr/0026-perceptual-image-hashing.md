# ADR 0026 — Read-only perceptual image hashing

Status: aceita. Milestone 5B. Implementa o contrato histórico da ADR 0025, que
permanece intacto. Schema v5; nenhuma tabela, migration, run, cache ou persistência.

## Unidade, leitura e saída

`dee media perceptual-hash --case-root /case` usa media_contents da 5A1, incluindo
singletons. A 5A continua verificando todas as fontes. Só o representative de
cada conteúdo elegível é reaberto para decode, por lookup nos registros Foundation
e confinamento de paths já existente. Conferir proveniência, size e SHA catalogados;
original_reader e sha256_stream revalidam bytes antes do decode, no mesmo handle,
com estabilidade conferida ao final inclusive quando o decode falha localmente.
Representatives são somente escolhas computacionais, sem preferência probatória.
Não há fallback para outra occurrence nem reextração, rematerialização ou temp image.

Um item por conteúdo, em ordem 5A1, com todas as occurrences, representative,
proveniência, status, width/height nullable, algorithm_id/version, phash_hex nullable,
error_code nullable e feature_class=DERIVED. Não recalcular por occurrence. JSON
compacto, ASCII/LF determinístico; sem relógio, pixels, thumbnail, EXIF, ICC, path
absoluto ou mensagens arbitrárias da biblioteca. Envelope expõe política/versões e
contagens de conteúdo, status e occurrences projetadas. Nenhum output em arquivo.

## Política image.phash / 1.0.0

Somente JPEG/PNG. Image.open deve reconhecer JPEG/PNG coerente com o conteúdo;
load completo é obrigatório. is_animated ou n_frames > 1 produz UNSUPPORTED,
incluindo APNG. LOAD_TRUNCATED_IMAGES não é habilitado. Guard de Pillow preservado:
DecompressionBombWarning é erro no escopo da operação, assim como
DecompressionBombError; MAX_IMAGE_PIXELS não é alterado pela aplicação.

EXIF orientation: ausência equivale a 1, valores inteiros 1–8 são suportados;
orientação inválida/ilegível falha explicitamente. ImageOps.exif_transpose aplica
a orientação. Width/height descrevem os pixels orientados antes do resize do hash.
Não expor outros EXIF. Alpha/transparency, inclusive RGBA, LA, paleta e tRNS,
é convertido a RGBA e composto com Image.alpha_composite sobre branco
(255,255,255,255); depois converter para RGB opaco. Sem alpha, converter para RGB.
ICC transform = none; não usar ImageCms. A versão inclui o comportamento dessas
conversões e arredondamentos de Pillow, conferido em fixtures sintéticas.

Chamar imagehash.phash com hash_size=8 e highfreq_factor=4 explícitos. A versão
instalada converte internamente para L, usa resize LANCZOS para 32×32 e DCT via
SciPy, produzindo 64 bits. Validar exatamente 16 caracteres [0-9a-f], preservando
zeros; representação incompatível é erro global, sem truncamento ou reparação.
Qualquer mudança relevante de pipeline/parâmetros/comportamento exige revisão da
versão semântica, que não se confunde com a versão da biblioteca.

## Dependências e reprodução

Diretas exatas: Pillow 12.3.0 e ImageHash 4.3.2. uv 0.8.22 adicionou somente elas
e as transitivas obrigatórias NumPy 2.5.3, SciPy 1.18.1 e PyWavelets 1.10.0;
os 24 pacotes preexistentes mantêm suas entradas no lock. PyWavelets é requisito
da metadata de ImageHash, não um algoritmo adicional implementado pelo motor.
Instalação por uv sync --locked --extra dev --python 3.12; Docker reconstruído,
sem rede em runtime. Nenhum extra opcional das bibliotecas é solicitado.

Metadata/licenças revisadas nos pacotes instalados: Pillow MIT-CMU; ImageHash
BSD-2-Clause; NumPy BSD-3-Clause com avisos de componentes 0BSD/MIT/Zlib/CC0;
SciPy BSD-3-Clause com licenças de componentes distribuídos; PyWavelets MIT e
BSD-3-Clause. Preservar os avisos dos wheels na distribuição, inclusive bibliotecas
nativas embarcadas. Fontes de metadata: [Pillow](https://pypi.org/pypi/Pillow/12.3.0/json)
e [ImageHash](https://pypi.org/pypi/ImageHash/4.3.2/json); o lock registra artefatos
e checksums, sem upgrades incidentais.

## Erros e interpretação

SUCCESS contém hash. FAILED é erro controlado de decode/normalização; UNSUPPORTED
é formato/recurso fora do contrato. Códigos locais fechados: DECODE_ERROR,
FORMAT_MISMATCH, INVALID_EXIF_ORIENTATION, DECOMPRESSION_BOMB,
ANIMATED_IMAGE_UNSUPPORTED, UNSUPPORTED_FORMAT e NORMALIZATION_ERROR.
Falhas mantêm occurrences e hash null; não há fallback. Erros operacionais de I/O,
schema, proveniência ou integridade são globais, nunca FAILED local.

Exit 0: todos os conteúdos tiveram sucesso, incluindo o conjunto vazio.
Exit 1: JSON completo confiável com algum FAILED/UNSUPPORTED.
Exit 2: erro global, sem conjunto parcial. Leitura não altera originais/working
intencionalmente; atime depende do filesystem/mount. Snapshot do catálogo e
estabilidade por arquivo não são promessa de snapshot atômico de todo o caso.

pHash é DERIVED, não prova igualdade, origem, upload, autoria ou contexto.
Sem threshold, score, classificação, clustering, Hamming ou matriz pairwise.
dHash fica adiado para estabilizar primeiro um único algoritmo/pipeline.

## Validação e limite de plataforma

Fixtures geradas artificialmente em runtime: JPEG/PNG, transformações,
orientações 1–8, alpha/paleta/LA, truncamento, APNG, guards e erros globais.
Goldens exclusivamente sintéticos, adicionados após comparação Windows/Linux
de hash, dimensões, status, pixels normalizados e serialização. Testes conferem
uma tentativa por representative, ausência de fallback, projeção e zero escrita.

O pipeline sintético é equivalente em Windows Python 3.12.11 e Linux 3.12.14
com o mesmo lock. A Foundation existente recusa arquivos no host quando stat e
fstat divergem em ctime; essa divergência também impede a paridade real no host
validado. Não alterar metadados ou enfraquecer o reader para contorná-la. A execução
integrada validada usa Linux; a comparação real Windows/Linux fica PARTIAL até
resolver a compatibilidade do runtime/Foundation em etapa explícita.
