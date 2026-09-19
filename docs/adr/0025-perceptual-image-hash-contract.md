# ADR 0025 — Perceptual image hash contract

Status: aceita como contrato futuro. Entrega: Milestone 5B0, somente documental.
Nenhum perceptual hash, código, dependência, schema ou migration é implementado.
Schema permanece v5. A arquitetura validada nas ADRs 0023/0024 é a entrada da 5B.

## Unidade de processamento e proveniência

Fluxo futuro: ExactMediaContent → representative occurrence → bytes verificados
→ decode completo → normalização determinística → resultado perceptual
→ projeção a todas as occurrences do exact content.

Calcular uma vez por SHA-256 distinto, incluindo singletons. Preservar todos os
IDs e vínculos de proveniência. O representative segue a ordenação da 5A1 e é
somente escolha computacional: não é evidência canônica, melhor imagem, fonte
preferida, ocorrência principal ou prova de autoria. Não escolher outro
representative silenciosamente em caso de erro.

Reutilizar a 5A1, que já verifica as occurrences pela 5A. Para decode, abrir apenas
o representative com as proteções da Foundation e revalidar size/SHA-256 e
estabilidade dos bytes usados; não confiar em validação anterior se houver mudança
concorrente. As demais occurrences não são decodificadas nem acessadas novamente
para recalcular perceptual hash. A verificação de integridade herdada da 5A continua
abrangendo todas elas. Nunca substituir o SHA-256 catalogado.

## Formatos, dependências e algoritmos

Primeira 5B: somente JPEG e PNG, formatos reconhecidos no conjunto validado da
5A1. GIF, WEBP, HEIC, HEIF, AVIF, MP4, MOV e ISO-BMFF genérico ficam excluídos;
expansão requer decisão futura explícita. Sem investigação de ISO-BMFF na 5B0.

Propor Pillow para decode e imagehash para pHash, algoritmo principal. dHash pode
entrar como segundo sinal técnico se o custo for pequeno; confirmar na implementação.
aHash não será critério principal. Sem score combinado.

Antes de incorporar bibliotecas na 5B, fixar versões em pyproject/uv.lock,
revisar licenças e dependências transitivas, validar instalação pelo lock
reproduzível e resultados em Windows/Linux. Nenhuma dependência de rede em runtime.
Nesta 5B0 não há seleção de versões, instalação, pesquisa web ou alteração do lock.

## Decode e normalização

1. Exigir decode completo por Pillow; assinatura reconhecida não garante imagem
   decodificável. Falha de decode produz FAILED para aquele conteúdo, com código
   técnico e sem hash; formato ou recurso fora do contrato produz UNSUPPORTED.
   Não inferir sucesso pela extensão nem gerar hash parcial. Erros de integridade
   dos bytes mantêm a falha técnica integral herdada da 5A.
2. Recusar animação/APNG como UNSUPPORTED, mesmo com extensão PNG. Não selecionar
   frame silenciosamente. JPEG/PNG com múltiplos frames exigem política futura.
3. Aplicar orientação EXIF válida e explicitamente suportada, preferencialmente
   via ImageOps.exif_transpose. A implementação deverá validar e testar as
   orientações suportadas; ausência mantém pixels como decodificados. Orientação
   presente inválida/não suportada gera FAILED/UNSUPPORTED explícito conforme
   a causa, sem correção inferida. Não extrair nem persistir outros campos EXIF.
4. O resultado é uma DERIVAÇÃO visual sobre pixels orientados; bytes originais
   ficam intactos e seu SHA-256 permanece o mesmo. A etapa de hash não consulta
   metadata. Não introduzir transformação automática por perfil ICC nesta versão.
5. Alpha: compor sobre branco fixo RGB (255, 255, 255), inclusive transparência
   de paleta, e produzir RGB opaco antes da conversão exigida pelo algoritmo.
   Não usar fundo do visualizador nem simplesmente descartar alpha. Esta é uma
   regra de produto, não uma afirmação sobre defaults de Pillow/imagehash;
   APIs, arredondamento e conversão de modos serão verificados em testes na 5B.
6. Fixar conversão de pixels, resize, parâmetros de hash e serialização antes de
   emitir a primeira versão. Não depender de defaults não documentados. Tudo em
   memória, sem modificar originais ou criar arquivos intermediários.

Width/height podem ser retornados como metadata DERIVED dos pixels orientados,
antes do resize do hash; não indicam identidade. Usar os guards de dimensões e
decompression bomb do Pillow escolhido. Não desabilitar warnings/guards
globalmente; tratar aviso/erro de limite como falha explícita do conteúdo.
Não fixar limites numéricos arbitrários nesta etapa; registrar os limites efetivos
da versão escolhida e testá-los antes de processar caso real.

## Resultado, versionamento e distância

Resultado conceitual por conteúdo: content_sha256, media_format, status,
width/height quando disponíveis, algorithm_id, algorithm_version e phash_hex em
sucesso. Em falha, hash ausente/null e código técnico, sem paths em mensagens.
Se dHash for incluído, seu dhash_hex deve ter identidade/versionamento próprios.
Projeção às occurrences preserva a associação ao conteúdo e o status, sem
transformar falha em ausência silenciosa. Todos os atributos perceptuais são DERIVED.

Identidades propostas para a primeira implementação: image.phash / 1.0.0 e,
se aprovado, image.dhash / 1.0.0. Não significam algoritmos já entregues.
A versão semântica identifica a política completa; não é apenas versão de biblioteca.
Mudanças relevantes em decode, orientação, alpha, resize/parâmetros ou comportamento
assumido das bibliotecas exigem nova versão. Registrar versões de dependências,
parâmetros, comprimento em bits e codificação hexadecimal determinística, com
largura fixa e zeros iniciais, para permitir reprodução.

Hamming distance conta bits distintos somente entre hashes bem-sucedidos do mesmo
algorithm_id/version e comprimento compatível. Não comparar pHash com dHash nem
falhas. Mesmo hash perceptual não prova mesma imagem; distância pequena não prova
duplicata; similaridade visual não estabelece origem, upload ou autoria.
Não definir threshold, score combinado ou classes same/similar/likely same.
Thresholds e clustering exigem milestone posterior com corpus controlado.

Uma matriz técnica read-only pode ser avaliada futuramente: por exemplo, 15
conteúdos geram 15 × 14 / 2 = 105 pares. Isso não autoriza engine pairwise nesta
5B0, persistência N² automática ou interpretação de relevância.

## Execução e validação futuras

Preferir primeira 5B read-only/in-memory. Persistência fica adiada; só justificar
com necessidade concreta de cache, auditoria ou reexecução e algoritmo/versões
estabilizados. Não antecipar schema v6. Outputs reais ficam fora do Git.

Criar somente na implementação fixtures inteiramente sintéticas JPEG/PNG cobrindo
imagem idêntica, cópia exata, recompressão JPEG, resize, pequenas mudanças de
brilho/contraste, crop, rotação/orientação, PNG alpha e imagem totalmente diferente.
Cobrir também corrupt/truncated, APNG recusado, decompression bomb guard e JSON
determinístico. Transformações medem comportamento técnico, sem prometer distância
ou equivalência. Validar bytes originais intactos, uma execução por conteúdo,
projeção integral e reprodutibilidade Windows/Linux com versões fixadas.

No caso real futuro: verify de todos os originais OK; obter exact contents via
5A1 e comparar contagens com o relatório externo validado; decodificar cada
representative uma vez, sem recalcular nas demais occurrences; projetar resultados
a todas elas, incluindo falhas explícitas; executar duas vezes e comparar JSON;
confirmar SHA/bytes/schema/table counts do banco e filesystem intactos; repetir
verify; produzir relatório externo com sucessos/falhas e limitações. Não prometer
preservação de atime além do mount. Não mostrar nem adicionar imagens, thumbnails,
pixels, hashes, paths, IDs ou dados pessoais reais ao Git. Nenhum caso real é
acessado ou processado nesta 5B0.

## Decisões a confirmar na implementação 5B

- Versões exatas Pillow/imagehash e transitivas, licenças e lock reproduzível.
- Parâmetros explícitos de pHash/resize/conversão, limites de decode efetivos e
  detalhes de arredondamento/composição alpha conforme a regra branca já decidida.
- Inclusão de dHash na primeira entrega e seus parâmetros/versionamento próprios.
- Envelope/exit status agregado para execução com falhas por conteúdo no caso real;
  FAILED/UNSUPPORTED sem hash por conteúdo já é obrigatório. Persistência continua
  adiada, com preferência read-only já definida.
