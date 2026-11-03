from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HelpTopic:
    id: str
    title: str
    html: str


_NOTE_STYLE = 'style="color:#8a94a6; margin-left: 4px;"'


def _note(text: str) -> str:
    return f'<p {_NOTE_STYLE}><i>Nota: {text}</i></p>'


HELP_TOPICS: list[HelpTopic] = [
    HelpTopic(
        id="inicio",
        title="Bem-vindo ao DocFlow",
        html=f"""
        <h2>O que é o DocFlow</h2>
        <p>O DocFlow ajuda um escritório de contabilidade a controlar, mês a mês, quais
        documentos cada empresa-cliente já entregou e quais ainda faltam - boletos,
        extratos bancários, notas fiscais, comprovantes, contratos etc. - e a organizar
        os arquivos recebidos automaticamente nas pastas certas.</p>

        <h3>Como este manual funciona</h3>
        <p>Cada item da lista à esquerda explica uma tela ou uma funcionalidade
        específica. Aperte <b>F1</b> a qualquer momento, em qualquer tela do programa,
        para abrir este manual já na página correspondente ao que você está usando.
        Use a caixa de busca no topo da lista para filtrar por palavra.</p>

        <h3>Navegação geral</h3>
        <ul>
        <li>O menu à esquerda é dividido em três grupos: <b>Acompanhamento</b> (o dia a
        dia), <b>Cadastros</b> (empresas e documentos) e <b>Administração</b> (só para
        administradores).</li>
        <li>No rodapé do menu ficam os botões <b>Banco</b> (backup e restauração - ver
        <a href="topic:backup">Banco de dados</a>) e <b>Ajuda</b> (este manual), o
        <b>Modo claro/escuro</b>, quem está conectado e o botão <b>Sair</b>.</li>
        </ul>

        <h3>As telas</h3>
        <ul>
        <li><b>Painel</b> - resumo do mês: quantas empresas entregaram tudo e quantas
        têm pendência.</li>
        <li><b>Panorama</b> - todas as empresas num mês e, ao clicar numa delas, o mapa
        dos documentos mês a mês, onde se marca Recebido, Pendente etc. É o ponto de
        partida do dia a dia.</li>
        <li><b>Cobranças</b> - o que está em aberto hoje, as cobranças feitas e os
        relatórios de verificação.</li>
        <li><b>Empresas</b> - lista e cadastro das empresas-cliente.</li>
        <li><b>Ficha da empresa</b> - como a empresa envia os documentos, o registro de
        cada documento e o histórico de cobranças.</li>
        <li><b>Documentos</b> - quais documentos cada empresa precisa entregar.</li>
        <li><b>Configurações</b>, <b>Usuários</b> e <b>Histórico de ações</b> -
        administração.</li>
        </ul>

        <h3>Primeiros passos</h3>
        <ol>
        <li>Os meses do ano são criados sozinhos ao abrir o DocFlow (o ano seguinte, a partir
        de novembro).</li>
        <li>Cadastre as empresas em <b>Empresas</b> (ou importe uma planilha).</li>
        <li>Em <b>Documentos</b>, cadastre o que cada empresa precisa entregar.</li>
        <li>No dia a dia, acompanhe pelo <b>Panorama</b>: clique numa empresa e marque os
        recebimentos direto no mapa, embaixo.</li>
        </ol>
        """,
    ),
    HelpTopic(
        id="login",
        title="Login e sessão",
        html="""
        <h2>Entrar no sistema</h2>
        <p>Informe <b>Nome de usuário</b> e <b>Senha</b> e clique em <b>Entrar</b> (ou
        aperte Enter). O botão <b>Sair</b> fecha o programa sem entrar.</p>

        <h3>Lembrar credencial neste computador</h3>
        <p>Marque <b>"Lembrar credencial neste usuário do computador"</b> antes de
        entrar para não precisar digitar a senha da próxima vez que abrir o DocFlow
        neste mesmo computador. Isso guarda um token de sessão local (não a senha em
        texto puro) vinculado a este usuário do sistema operacional.</p>
        <ul>
        <li>Desmarcar a opção e entrar de novo revoga esse "lembrar" em qualquer lugar
        onde ele estivesse ativo para essa conta.</li>
        <li>Trocar a senha do usuário (própria ou feita por um admin em
        <a href="topic:usuarios">Usuários</a>) também revoga automaticamente qualquer
        sessão lembrada dessa conta - por segurança.</li>
        </ul>

        <h3>Encerrar sessão</h3>
        <p>Use o botão <b>Sair</b> no rodapé do menu lateral. Ele pergunta
        confirmação, revoga a credencial lembrada (se houver) e volta para a tela de
        login.</p>
        """,
    ),
    HelpTopic(
        id="dashboard",
        title="Painel",
        html="""
        <h2>Para que serve</h2>
        <p>A primeira tela do dia. No topo, <b>Cobrança agora</b>: o funil com quantos
        documentos estão em cada etapa (Verificar, Cobrar, Recobrar, Aguardando, Com uma
        pessoa), quantos casos esperam você em <a href="topic:atencao">Precisa de atenção</a>
        e como terminou a última rodada do Claude. Clique numa etapa ou num cartão para ir
        direto para a lista certa.</p>
        <p>Embaixo, <b>Entrega do mês</b>: quantas empresas estão em cada situação no mês
        escolhido e como andou a conclusão nos últimos meses. Para marcar documentos use o
        mapa do <a href="topic:panorama">Panorama</a>.</p>

        <h3>Controles</h3>
        <ul>
        <li><b>Competência</b> - o mês a resumir.</li>
        <li><b>Somente empresas ativas</b> - desmarque para incluir as inativas.</li>
        <li><b>Atualizar</b> - recarrega os números.</li>
        </ul>

        <h3>Os 6 cartões</h3>
        <ul>
        <li><b>Empresas no período</b> - total considerado.</li>
        <li><b>Concluídas</b> - nenhum documento do mês em aberto.</li>
        <li><b>Em andamento</b> - parte dos documentos já marcada.</li>
        <li><b>Dentro do prazo</b> - nada marcado ainda, mas o prazo de cobrança do
        mês não acabou.</li>
        <li><b>Com pendência</b> - algum documento marcado como "Pendente".</li>
        <li><b>Em atraso</b> - o prazo de cobrança do mês acabou sem tudo resolvido
        (os prazos ficam em <a href="topic:configuracoes">Configurações</a>).</li>
        </ul>

        <h3>Gráficos</h3>
        <ul>
        <li><b>Distribuição por situação</b> - proporção de cada situação acima.</li>
        <li><b>Conclusão das últimas 6 competências</b> - em cada mês, quanto dos
        documentos já teve alguma decisão (Recebido, Pendente ou Encerrado).</li>
        </ul>
        """ + _note(
            "sem nenhum mês cadastrado o Painel fica vazio - gere os meses do ano em "
            "Panorama &gt; Ferramentas &gt; \"Gerar os meses de um ano...\"."
        ),
    ),
    HelpTopic(
        id="panorama",
        title="Panorama",
        html="""
        <h2>Para que serve</h2>
        <p>Todas as empresas de uma vez, num mês escolhido, já mostrando o que ficou
        em aberto de meses anteriores. É o ponto de partida do dia a dia.</p>

        <h3>Filtros</h3>
        <ul>
        <li><b>Competência</b> - o mês a conferir.</li>
        <li><b>Buscar empresa</b> - por código ou nome.</li>
        <li><b>Somente ativas</b> - marcado por padrão.</li>
        <li>Clique com o botão direito no <b>cabeçalho de uma coluna</b> para filtrar
        pelos valores dela (ex: só quem está "Com pendência"). <b>Limpar filtros</b>
        desfaz.</li>
        </ul>

        <h3>Colunas</h3>
        <ul>
        <li><b>Situação do mês</b> - só o mês escolhido.</li>
        <li><b>Progresso</b> - barra com os documentos do mês: verde recebidos, vermelho
        pendentes, cinza encerrados/não cobrar; o número é marcados sobre o total (ex: 5/7).</li>
        <li><b>Meses anteriores em aberto</b> - quantos meses <i>antes</i> do escolhido
        ainda têm documento sem receber, e desde quando (ex: "3 meses (desde 07/2026)").
        Passe o mouse para ver a lista.</li>
        <li><b>Última marcação</b> - quem mexeu por último e quando.</li>
        </ul>

        <h3>Marcar documentos (o mapa da empresa)</h3>
        <p>Clique numa empresa: embaixo aparece o mapa dela, com os 12 meses até a
        competência escolhida no topo. Cada linha é um documento (agrupados por tipo) e cada
        quadradinho é um mês, na cor do status: <b>&#10003;</b> verde Recebido,
        <b>!</b> vermelho Pendente, cinza Encerrado, ponto Não cobrar. Um ponto colorido no
        canto mostra a situação da cobrança (vermelho: precisa de uma pessoa ou a verificação
        falhou; amarelo: não encontrado ou com problema; azul: cobrado, aguardando). Passe o
        mouse num quadradinho para ver quem marcou e quando.</p>
        <ol>
        <li><b>Escolha</b> o que marcar: clique num quadradinho. Para vários: Ctrl+clique
        (soma), Shift+clique (de um até outro), clique no <b>mês</b> (a coluna toda) ou no
        <b>nome do documento</b> (a linha toda). Esc desmarca.</li>
        <li><b>Marque</b> com os botões acima do mapa ou digitando, como na planilha:
        <b>Recebido</b> (O de "OK", ou R), <b>Pendente</b> (P), <b>Não cobrar</b> (X, ou N),
        <b>Encerrado</b> (E) ou <b>Limpar</b> (Del). As <b>setas</b> andam para o quadradinho
        ao lado (pulando os que não se aplicam), então dá para preencher a linha toda só pelo
        teclado. O botão direito do mouse abre as mesmas opções.</li>
        <li><b>Arrastar para preencher</b>, como no Excel: clique num quadradinho marcado,
        pegue a alça no canto de baixo (o mouse vira um <b>+</b>) e arraste para o lado - os
        próximos meses ficam com o mesmo status - ou para cima/baixo, para os outros
        documentos do mesmo mês. Vale para Recebido, Pendente e Não cobrar.</li>
        <li><b>Copiar e colar</b> (Ctrl+C / Ctrl+V), como numa planilha: selecione os
        quadradinhos, Ctrl+C, clique onde quer colar e Ctrl+V - cola a partir dali, no mesmo
        formato. Um status só colado em vários selecionados preenche todos. Também aceita o
        que vem do Excel (Recebido/OK, Pendente, Não cobrar/X, Encerrado). Esc tira o
        tracejado do que foi copiado.</li>
        <li><b>Desfazer</b> (Ctrl+Z): volta a última marcação feita no mapa (marcar, arrastar ou
        colar). Dá para apertar várias vezes, até as últimas 20.</li>
        <li>Para registrar mais do que o status (chegou errado, o cliente prometeu, precisa
        de uma pessoa, com observação e arquivo), use <b>Resolver...</b>.</li>
        </ol>
        <p><b>Encerrado</b> faz o documento parar de ser cobrado a partir daquele mês: os
        meses seguintes ficam tracejados e não podem ser marcados. Quadradinho tracejado
        também aparece quando o documento não é cobrado naquele mês pela regra do tipo
        (mensal, trimestral ou anual em janeiro - veja em <a href='topic:documentos'>Documentos</a>).
        Empresas inativas aparecem, mas não podem ser marcadas.</p>
        <p>Ao lado do mapa fica o detalhe do que está selecionado: com um quadradinho, o
        status, quem marcou e tudo o que aconteceu naquele mês (cobranças, verificações, o
        arquivo baixado); sem seleção, o resumo da empresa. <b>Abrir na ficha</b> leva para a
        <a href="topic:ficha">Ficha da empresa</a> já no documento e mês selecionados.
        <b>Pasta da empresa...</b> define a pasta no computador onde ficam os documentos
        dela.</p>

        <h3>Menu Ferramentas</h3>
        <ul>
        <li><b>Imprimir ou exportar relatório de pendências</b> - escolha os meses (De /
        até) e as empresas, e use <b>Imprimir</b> (vai direto para a impressora),
        <b>Salvar PDF</b> ou <b>Salvar Excel</b>. Ao salvar, o DocFlow oferece abrir o
        arquivo.</li>
        <li><b>Gerar os meses de um ano</b> - cria as 12 competências de um ano. Normalmente
        não precisa: ao abrir, o DocFlow cria sozinho os meses do ano atual e, a partir de
        novembro, os do ano seguinte, para janeiro já chegar pronto. Use para um ano
        anterior que ainda não está no sistema.</li>
        <li><b>Excluir os meses de um ano</b> - apaga um ano inteiro com os status
        marcados nele (empresas e documentos continuam).</li>
        <li><b>Preparar email de cobrança</b> e <b>Copiar mensagem de WhatsApp</b> -
        texto pronto cobrando o que está em aberto da empresa selecionada.</li>
        </ul>
        """,
    ),
    HelpTopic(
        id="cobrancas",
        title="Cobranças",
        html="""
        <h2>Para que serve</h2>
        <p>É a memória da cobrança. Tudo o que o Claude (pelo servidor MCP) ou uma pessoa
        faz fica anotado aqui: cada verificação, cada cobrança e em que situação cada
        documento está. É com essas anotações que o sistema decide o próximo passo.</p>

        <h3>O que fazer agora</h3>
        <p>Uma linha por documento em aberto, com a ação certa pelas regras do sistema e o
        porquê. No topo, o <b>funil</b> mostra quantos documentos há em cada etapa; clique
        numa etapa para ver só ela e clique de novo para ver tudo:</p>
        <ul>
        <li><b>Verificar</b> - ainda não foi conferido, ou já passou o prazo depois da
        cobrança, ou a última verificação falhou;</li>
        <li><b>Cobrar</b> - foi procurado e não estava lá, e nunca foi cobrado;</li>
        <li><b>Recobrar</b> - já foi cobrado, o prazo de espera passou e continua faltando;</li>
        <li><b>Aguardando</b> - cobrado há pouco, ou o cliente prometeu enviar até uma data;</li>
        <li><b>Com uma pessoa</b> - algo que o Claude não deve decidir sozinho (veja
        <a href="topic:atencao">Precisa de atenção</a>).</li>
        </ul>
        <p>Os prazos e limites vêm de <a href="topic:configuracoes">Configurações &gt; Depois
        de cobrar</a>. Selecione um ou vários documentos e use <b>Resolver...</b> para dizer
        o que aconteceu (veja abaixo); <b>Abrir na ficha</b> (ou clique duplo) leva para a ficha
        já no documento e no mês. <b>Registrar cobrança...</b> registra uma cobrança feita por fora
        (email, WhatsApp, telefone); a primeira de um documento num mês é <i>cobrança</i>, as
        seguintes são <i>recobranças</i>.</p>


        <h3>Resolver documento</h3>
        <p>A mesma janela aparece em Cobranças, Precisa de atenção e na Ficha. Escolha o que
        aconteceu e, se quiser, escreva uma <b>observação</b> (fica no histórico do documento):</p>
        <ul>
        <li><b>Chegou e está certo</b> - dá baixa (Recebido). Dá para indicar o arquivo;</li>
        <li><b>Chegou, mas está errado</b> - escolha o que está errado (documento, competência,
        ilegível, de outra empresa) e indique o arquivo;</li>
        <li><b>Não chegou</b> - vai para a fila de cobrança;</li>
        <li><b>O cliente prometeu enviar</b> - escolha a data; até lá ninguém cobra;</li>
        <li><b>Precisa de uma pessoa</b> - tira do fluxo do Claude, com o motivo;</li>
        <li><b>Devolver para o Claude</b> - só para casos que estão com uma pessoa: volta a ser
        verificado e cobrado.</li>
        </ul>
        <p>Selecionando vários documentos (Ctrl ou Shift), a mesma resposta vale para todos.</p>

        <h3>Conferências feitas</h3>
        <p>O relatório de cada conferência nos canais de uma empresa, com contadores e um
        bloco para cada resultado:</p>
        <ul>
        <li><b>Recebidos e baixados</b> - achados e já marcados como Recebido;</li>
        <li><b>Encontrados sem baixa</b> - achados, mas a baixa não foi feita (o erro fica
        anotado). Use <b>Dar baixa no que foi encontrado</b>;</li>
        <li><b>Com problema</b> - chegou algo, mas errado (outro documento, outra
        competência, ilegível, de outra empresa);</li>
        <li><b>Não encontrados</b> - procurou e não estava lá: vão para cobrança;</li>
        <li><b>Verificação falhou</b> - não deu para olhar (sem acesso, sistema fora do ar).
        Isso <i>não</i> gera cobrança: o documento só volta a ser verificado.</li>
        </ul>
        <p>Quando o documento foi baixado, o relatório mostra o nome do arquivo com os links
        <b>abrir documento</b> e <b>abrir pasta</b>, para você conferir o arquivo na hora.</p>
        <p>O filtro <b>Com algo a resolver</b> mostra só as verificações com problema,
        falha ou baixa pendente.</p>

        <h3>Cobranças enviadas</h3>
        <p>Todas as cobranças registradas, com canal, documentos e a mensagem enviada.</p>

        <h3>Rodadas do Claude</h3>
        <p>Cada passada do Claude pelas cobranças é uma rodada: quando começou e terminou,
        quantas empresas, verificações e cobranças, e as falhas e avisos que ele anotou.
        Uma rodada que começou e nunca terminou aparece como <b>Interrompida</b>.</p>
        """,
    ),
    HelpTopic(
        id="atencao",
        title="Precisa de atenção",
        html="""
        <h2>Para que serve</h2>
        <p>Aqui fica o que precisa de uma pessoa. O menu mostra quantos casos estão
        esperando, em vermelho.</p>

        <h3>Documentos</h3>
        <p>Documentos tirados do fluxo automático, cada um com o motivo:</p>
        <ul>
        <li>o Claude achou o documento, mas a baixa não pôde ser feita;</li>
        <li>chegou o documento errado (se a regra mandar para uma pessoa);</li>
        <li>o limite de recobranças foi atingido sem resposta;</li>
        <li>o Claude encaminhou o caso, por exemplo porque o cliente respondeu algo que
        precisa de decisão ou porque estava em dúvida.</li>
        </ul>
        <p>Clique num documento para ver o motivo, <b>o que fazer</b> naquele tipo de caso e tudo
        o que aconteceu com ele. <b>Abrir documento</b> e <b>Abrir pasta</b> abrem o arquivo que o
        Claude baixou (ou a pasta da empresa). Você pode selecionar
        vários de uma vez (Ctrl ou Shift) e usar <b>Resolver...</b>: diga como terminou
        (chegou, chegou errado, cliente prometeu...) ou <b>Devolver para o Claude</b>, quando o
        que travava foi resolvido e o documento deve voltar a ser verificado e cobrado.
        <a href="topic:cobrancas">Veja todas as opções</a>. <b>Abrir ficha</b> vai para a ficha
        já no documento.</p>

        <h3>Rodadas com problema</h3>
        <p>Rodadas do Claude dos últimos 7 dias que registraram falhas (email fora do ar,
        sem acesso ao Onvio...) ou que começaram e nunca terminaram. O histórico completo
        fica em <a href="topic:cobrancas">Cobranças &gt; Rodadas do Claude</a>.</p>
        """,
    ),
    HelpTopic(
        id="ficha",
        title="Ficha da empresa",
        html="""
        <h2>Para que serve</h2>
        <p>Tudo sobre uma empresa num lugar só. Escolha a empresa no topo (ou use
        <b>Abrir ficha</b> em Empresas, Panorama ou Cobranças). Os cartões mostram quantos
        documentos estão em aberto, quantas cobranças e recobranças foram enviadas e a
        data do último contato.</p>

        <h3>Visão geral</h3>
        <p>O panorama da empresa: o mapa dos meses (uma linha por documento, um
        quadradinho por mês, na cor do status, com um ponto quando há algo na cobrança) e a
        lista <b>Em aberto agora</b>, com a próxima ação de cada documento. Clique num
        quadradinho ou dê dois cliques na lista para abrir o histórico; selecione itens da
        lista e use <b>Resolver...</b> para dizer o que aconteceu.</p>
        <p>Acima do mapa, escolha o que ver: <b>Últimos 12 meses</b> (o padrão, que atravessa
        a virada do ano) ou um ano inteiro, de janeiro a dezembro. As setas <b>‹ ›</b> andam
        de um ano para o outro.</p>

        <h3>Documentos</h3>
        <p>Cada documento da empresa com o status no mês atual, a <b>próxima ação</b> (a
        mais urgente entre as competências em aberto) e quantas vezes foi cobrado e
        recobrado. Clique num documento para ver o <b>registro dele</b>, mês a mês: status,
        situação de cobrança, cobranças, recobranças e a última verificação. Clique numa
        competência para ver, ao lado, tudo o que aconteceu com ela em ordem. Ali
        mesmo: <b>Abrir documento</b> abre o arquivo baixado na última verificação, <b>Abrir
        pasta</b> abre a pasta dele (ou a pasta da empresa), e <b>Resolver...</b> registra o
        que aconteceu naquele mês.</p>

        <h3>Como receber</h3>
        <p>Por quais canais a empresa envia os documentos (Email, Onvio...), de quais
        emails eles chegam e instruções livres de onde procurá-los. É com essas
        informações que o Claude verifica se os documentos chegaram antes de cobrar.</p>

        <h3>Histórico</h3>
        <p>Cobranças, recobranças e verificações da empresa, da mais recente para a mais
        antiga. Clique num evento para ver os detalhes (destinatário, mensagem, documentos,
        o que foi encontrado).</p>
        """,
    ),
    HelpTopic(
        id="empresas",
        title="Empresas",
        html="""
        <h2>Para que serve</h2>
        <p>Lista e cadastro das empresas-cliente.</p>

        <h3>Encontrar e editar</h3>
        <ul>
        <li>A lista mostra todas as empresas ativas; use a busca (código, nome ou CNPJ)
        e <b>Mostrar inativas</b> para ver as inativas também.</li>
        <li>Clique numa empresa: o cadastro aparece ao lado, já pronto para editar.
        Mude o que precisar e clique em <b>Salvar alterações</b> (ou <b>Descartar</b>).</li>
        <li><b>Nova empresa</b> abre um cadastro em branco.</li>
        <li><b>Abrir ficha</b> leva à <a href="topic:ficha">Ficha da empresa</a>.</li>
        <li><b>Mais ações</b>: <i>Inativar/Reativar</i> (tira das listas e cobranças sem
        apagar nada), <i>Remover dados de contato (LGPD)</i> e <i>Excluir empresa</i>
        (apaga de vez, com documentos e histórico).</li>
        </ul>

        <h3>Campos</h3>
        <ul>
        <li><b>Código</b> e <b>Nome</b> - obrigatórios; o código não muda depois.</li>
        <li><b>CNPJ</b> - opcional; aceita o formato tradicional e o novo alfanumérico.</li>
        <li><b>Contato para cobrança</b> - nome, email e WhatsApp usados nas cobranças
        (mais de um email: separe por vírgula, e a cobrança vai para todos; o WhatsApp aceita "(27) 99999-8888"; sem DDI o sistema põe o +55). A opção de não
        incluir na mala direta tira a empresa das malas diretas de
        <a href="topic:envios">Envios automáticos</a>.</li>
        <li><b>Prazos de cobrança</b> - por padrão a empresa segue os prazos gerais de
        <a href="topic:configuracoes">Configurações</a>. Marque <i>Usar prazos próprios</i>
        só se ela precisar de datas diferentes.</li>
        <li><b>Observação</b> - texto livre, até 255 caracteres.</li>
        </ul>

        <h3>Importar planilha</h3>
        <p><b>Importar planilha</b> cadastra ou atualiza várias empresas (e seus
        documentos) de uma vez. No mesmo menu dá para ver as colunas esperadas e baixar
        uma planilha modelo.</p>
        """,
    ),
    HelpTopic(
        id="documentos",
        title="Documentos",
        html="""
        <h2>Para que serve</h2>
        <p>Define <b>o que cada empresa precisa entregar</b> - a lista que depois aparece
        no mapa do <a href="topic:panorama">Panorama</a>.</p>

        <h3>Cadastrar</h3>
        <ol>
        <li>Escolha a empresa no topo - a lista mostra os documentos dela.</li>
        <li>Clique em <b>Novo documento</b>.</li>
        <li><b>Tipo</b> - ex: Extratos CC, Contratos. O sistema já vem com Extratos CC e
        Extratos aplicacao (mensais), Informe de Rendimentos (trimestral), CRM e CRO (anuais). <b>Tipos...</b> cadastra novos e
        define a regra de cada tipo: <i>Mensal</i>, <i>Trimestral</i> (março, junho,
        setembro, dezembro) ou <i>Anual em janeiro</i> (nos outros meses fica "Não cobrar"
        sozinho).</li>
        <li><b>Nome</b> - curto e sem repetir o tipo: o tipo já diz o que é, o nome diz
        de onde (ex: tipo Extratos CC, nome Banco do Brasil). Digite ou escolha um dos nomes
        sugeridos. <b>Nomes padrão...</b> mantém essa lista de sugestões.</li>
        <li><b>Recebe por</b> - marque por onde o documento costuma chegar (Email,
        Onvio...). <b>Gerenciar meios...</b> cadastra outros meios.</li>
        <li><b>Observação</b> - o detalhe que não cabe no nome: número da conta, produto
        da aplicação, contrato do empréstimo, quem envia. Aparece na Ficha, no Panorama e na
        lista do que cobrar (e o Claude usa para achar o documento).</li>
        <li>Clique em <b>Cadastrar documento</b>.</li>
        </ol>

        <h3>Editar e excluir</h3>
        <p>Clique num documento da lista para editar ao lado e <b>Salvar alterações</b>.
        Para excluir vários, selecione-os com Ctrl ou Shift.</p>
        """ + _note(
            "excluir um documento apaga junto todo o histórico de status e de cobranças "
            "dele. Não tem como desfazer."
        ) + """
        <h3>Importar planilha</h3>
        <p>Com a empresa escolhida, <b>Importar planilha</b> cadastra vários documentos
        de uma vez (tipos que não existirem são criados). No mesmo menu dá para ver as
        colunas e baixar a planilha modelo.</p>
        """,
    ),
    HelpTopic(
        id="configuracoes",
        title="Configurações",
        html="""
        <h2>Para que serve</h2>
        <p>Regras que valem para o escritório inteiro (só administradores).</p>

        <h3>Prazos de cobrança</h3>
        <p>Para cada mês, os documentos são cobrados no mês seguinte: a cobrança
        começa no dia escolhido em <b>Começar a cobrar no</b>, o prazo vai até o dia de
        <b>Prazo final de entrega</b>; depois dele, o que faltar fica <b>Em atraso</b>.
        <b>Priorizar depois de</b> diz quantos dias de atraso esperar antes de tratar o caso
        como prioridade de cobrança. A tela mostra um
        exemplo com os valores escolhidos. Empresas com prazos próprios (definidos no
        cadastro em <a href="topic:empresas">Empresas</a>) não seguem esta regra.</p>

        <h3>Depois de cobrar</h3>
        <p>As regras que decidem o próximo passo de cada documento (o Claude segue
        exatamente estas regras):</p>
        <ul>
        <li><b>Esperar depois de cobrar</b> - quantos dias o documento fica aguardando antes
        de ser verificado e, se ainda faltar, recobrado;</li>
        <li><b>Recobrar no máximo</b> - depois de tantas recobranças sem resposta, o caso vai
        para uma pessoa em <a href="topic:atencao">Precisa de atenção</a>;</li>
        <li><b>Documento que chegar errado vai direto para uma pessoa</b> - desmarcado, um
        documento errado é cobrado de novo como se não tivesse chegado.</li>
        </ul>

        <h3>Mala direta</h3>
        <p>Agora fica em <a href="topic:envios">Envios automáticos</a>, com as mesmas regras
        de competência, email e WhatsApp das cobranças.</p>

        <h3>Claude (MCP)</h3>
        <p>Liga o DocFlow ao Claude Desktop: clique em <b>Conectar ao Claude Desktop</b>. Não
        precisa de usuário nem senha - o que o Claude fizer aparece no Histórico de ações como
        <b>claude</b>.</p>
        <ul>
        <li>A tela mostra <b>onde o Claude lê a configuração</b> neste computador. O Claude da
        Microsoft Store e o do site usam arquivos diferentes; o Conectar grava nos dois e
        guarda uma cópia do arquivo anterior.</li>
        <li>Se aparecer <b>Aponta para outro lugar</b>, a configuração é de uma pasta antiga ou
        de outra instalação (comum em computador reaproveitado): clique em Conectar para
        corrigir.</li>
        <li>Depois de conectar, feche o Claude de vez (ícone perto do relógio &gt; Sair) e
        abra de novo.</li>
        <li><b>Copiar configuração</b> serve para colar à mão no Claude, em Configurações &gt;
        Desenvolvedor &gt; Editar configuração.</li>
        </ul>
        """,
    ),
    HelpTopic(
        id="usuarios",
        title="Usuários",
        html="""
        <h2>Para que serve</h2>
        <p>Quem pode entrar no DocFlow (só administradores veem esta tela).</p>

        <h3>Criar ou editar</h3>
        <ul>
        <li><b>Novo usuário</b> abre um cadastro em branco: nome, perfil, senha (duas
        vezes) e se pode entrar.</li>
        <li>Clique num usuário da lista para editar. Deixe a senha em branco para
        manter a atual.</li>
        <li>Perfis: <b>Administrador</b> pode tudo; <b>Usuário comum</b> usa o dia a dia,
        sem mexer em usuários, configurações e backups.</li>
        </ul>

        <h3>Desativar em vez de excluir</h3>
        <p>Não existe exclusão de usuário - desmarque <i>Pode entrar no sistema</i> e
        salve. O histórico de ações dele continua guardado.</p>

        <h3>Proteções</h3>
        <ul>
        <li>Você não pode inativar nem tirar o próprio perfil de administrador.</li>
        <li>Sempre fica pelo menos um administrador ativo.</li>
        <li>Trocar a senha ou inativar um usuário encerra os acessos lembrados dele.</li>
        </ul>
        """,
    ),
    HelpTopic(
        id="envios",
        title="Envios automáticos",
        html="""
        <h2>Para que serve</h2>
        <p>Cobranças e malas diretas que saem sempre nas mesmas épocas - por exemplo, cobrar
        o <b>Informe de Rendimentos</b> de cada trimestre ou mandar a <b>distribuição de
        lucros</b> todo mês. Cada envio sabe para quem vai, de quais competências, quando e
        com que texto; os emails saem pelo email do escritório (com um clique) ou pelo
        Claude, e as conversas de WhatsApp abrem prontas, uma a uma. Tudo fica registrado
        (só administradores).</p>

        <h3>A tela</h3>
        <p>À esquerda ficam <b>todos os envios</b>, com um aviso de quantas empresas estão
        <b>para enviar</b> agora (ou <i>Em dia ✓</i>). Clique num envio e, à direita,
        aparecem três abas:</p>
        <ul>
        <li><b>Quem recebe</b>: escolha a competência e veja, separado, quem recebe por
        <b>Email</b>, quem recebe por <b>WhatsApp</b> e quem <b>Fica de fora</b> (e por quê:
        já entregou o documento, sem contato, tirada do envio...). Clique numa empresa para
        ver a mensagem exata que ela recebe.</li>
        <li><b>Mensagem</b>: o assunto, o texto do email e um texto próprio para o WhatsApp
        (vazio = o mesmo do email). Os botões <b>{empresa}</b>, <b>{contato}</b>,
        <b>{documentos}</b>... inserem o campo onde está o cursor.</li>
        <li><b>Formatar o email</b>: selecione o texto e use os botões <b>N</b> (negrito),
        <i>I</i> (itálico) e <u>S</u> (sublinhado), ou Ctrl+B, Ctrl+I e Ctrl+U.
        <b>Prévia do email</b> mostra como ele chega, já com a assinatura. No WhatsApp o
        negrito vira *assim* e o itálico _assim_.</li>
        <li><b>Assinatura</b>: em <b>Email de envio...</b> (no alto da tela). Vai no fim de
        todo email que o DocFlow envia.</li>
        <li><b>Histórico</b>: tudo o que já foi enviado neste envio.</li>
        </ul>

        <h3>Tudo por competência</h3>
        <p>Como na contabilidade, o envio diz <b>quais competências</b> cobrar, não em que mês
        enviar. O informe do trimestre que fecha em dezembro só fica pronto no fim de
        dezembro, então a competência 12 é cobrada em <b>janeiro</b>. Por isso o padrão é
        <i>No mês seguinte à competência</i>: competências 3, 6, 9 e 12 saem em abril,
        julho, outubro e janeiro, a partir do dia escolhido. Use <i>No próprio mês</i> só
        para avisos que precisam sair dentro da competência.</p>

        <h3>Criar um envio</h3>
        <p><b>Novo envio</b> oferece três modelos: <i>Cobrança de documento</i> (vai para as
        empresas que têm aquele tipo de documento e ainda não entregaram), <i>Mala direta em
        cópia oculta</i> e <i>Aviso para empresas escolhidas</i>. <b>Editar...</b> muda
        público, competências, dia, canal e textos.</p>
        <ul>
        <li><b>Canal Automático</b>: vai por WhatsApp para as empresas que liberaram o
        WhatsApp para envios (veja abaixo) e por email para as demais. Dá para forçar só
        email ou só WhatsApp.</li>
        <li>A mensagem entra na lista a partir do dia escolhido e fica lá até ser enviada.</li>
        </ul>

        <h3>Incluir e tirar empresas</h3>
        <p>Em <b>Quem recebe</b>, selecione empresas e clique em <b>Tirar deste envio</b> -
        vale para qualquer envio, inclusive a cobrança do informe: a empresa continua com o
        documento, só deixa de receber aquele envio. Ela vai para <i>Fica de fora</i> com o
        motivo <i>Tirada deste envio</i>, e <b>Incluir de volta</b> desfaz. Na mala direta,
        <b>Incluir empresas...</b> põe clientes novos na lista.</p>

        <h3>WhatsApp: quem pode receber</h3>
        <p>Na tela <b>Empresas</b>, em <i>Contato para cobrança</i>, marque <b>Pode usar o
        WhatsApp nos envios</b> - sem essa marcação nada vai por WhatsApp para a empresa.
        Empresas atendidas num <b>grupo</b> guardam o link do grupo (no WhatsApp: abra o
        grupo &gt; Convidar via link &gt; Copiar link); com ele, os envios abrem o grupo em
        vez da conversa com o número.</p>

        <h3>Enviar</h3>
        <ul>
        <li><b>Email - Enviar emails agora</b>: o DocFlow envia sozinho pelo email do
        escritório e registra cada empresa. Configure uma vez em <b>Email de envio...</b>
        (no alto da tela): escolha o provedor, informe email e senha e clique em <i>Enviar
        email de teste</i>. No Gmail e no Microsoft 365 use uma <b>senha de app</b>.</li>
        <li><b>Abrir no meu email</b> monta o rascunho no seu programa de email, se preferir
        enviar você mesmo.</li>
        <li><b>WhatsApp - Enviar em sequência</b>: abre uma conversa por vez, já com a
        mensagem escrita; você confere, aperta enviar no WhatsApp, volta e clica em
        <b>Enviei</b> - o envio fica registrado e a próxima abre sozinha. Nos grupos o
        WhatsApp não aceita texto pronto: a mensagem vai <b>copiada</b>, é só colar
        (Ctrl+V) no grupo e enviar.</li>
        <li><b>Marcar como enviado</b> registra o que foi enviado por fora.</li>
        </ul>

        <h3>Mala direta em cópia oculta</h3>
        <p>Como o escritório já faz: <b>um email só</b>, para o email do escritório (campo
        <i>Para</i>, na aba Mensagem), com os clientes em <b>cópia oculta</b> - ninguém vê o
        email dos outros. Todo mês sai com a competência do mês anterior. Quem liberou o
        WhatsApp sai da cópia oculta e recebe a mensagem no WhatsApp. Listas grandes são
        divididas em vários emails iguais automaticamente.</p>

        <h3>Modelos de texto</h3>
        <p>Na aba Mensagem, <b>Modelos de texto</b> guarda o texto atual com um nome e
        carrega qualquer modelo guardado em outro envio - bom para textos que se repetem
        (informe, distribuição de lucros, avisos).</p>

        <p><b>Histórico</b> (aba no alto) mostra tudo o que foi enviado, por qual canal, e o
        que falhou (com o motivo), com filtro por envio. Uma mesma mensagem nunca vai duas
        vezes para a mesma empresa na mesma competência.</p>
        """ + _note("empresa sem email ou WhatsApp cadastrado aparece em vermelho e não recebe nada até o contato ser cadastrado."),
    ),
    HelpTopic(
        id="logs",
        title="Histórico de ações",
        html="""
        <h2>Para que serve</h2>
        <p>Tudo o que foi feito no sistema, do mais recente para o mais antigo: quem
        fez, o quê, quando e em qual empresa (só administradores).</p>

        <h3>Filtrar</h3>
        <p>Escolha <b>Empresa</b>, <b>Ano</b> e <b>Mês</b> - a lista atualiza na hora.
        <b>Limpar filtros</b> volta a mostrar tudo. Aparecem no máximo os 500 registros
        mais recentes de cada vez.</p>

        <h3>Apagar registros antigos</h3>
        <p><b>Apagar registros antigos...</b> (no rodapé) remove de vez registros mais
        velhos que o número de dias informado - existe para atender a LGPD.</p>
        """ + _note("não dá para desfazer - confira o prazo antes de confirmar."),
    ),
    HelpTopic(
        id="backup",
        title="Banco de dados: backup e troca",
        html="""
        <h2>Backup manual</h2>
        <p>Botão <b>Banco</b>, no rodapé do menu lateral &gt; <b>Fazer backup agora...</b>
        - escolha onde salvar e pronto.</p>

        <h3>Backup automático</h3>
        <p><b>Banco &gt; Backup automático...</b> abre uma tela onde
        você ativa, escolhe a pasta, de quanto em quanto tempo gerar um novo backup
        (contado a partir do último, automático ou manual - não é um horário fixo do
        dia) e quantos backups antigos manter naquela pasta (os mais antigos são
        apagados sozinhos só ali; backups manuais ou em outra pasta nunca são
        tocados).</p>
        <p>Opcionalmente, defina uma <b>senha de criptografia</b> - vale pra todos os
        backups (automáticos e manuais) e será exigida pra restaurar qualquer um
        deles depois. Se perder essa senha, o backup criptografado fica
        irrecuperável.</p>
        """ + _note(
            "o backup automático só roda enquanto o programa está aberto: ao abrir o "
            "DocFlow, se já passou do intervalo configurado, um novo backup é gerado "
            "na hora, em segundo plano."
        ) + """
        <h3>Restaurar um backup</h3>
        <p><b>Banco &gt; Restaurar backup...</b> (só admin) - escolha o arquivo
        de backup. Pede confirmação dupla, porque <b>substitui todos os dados atuais
        do banco em uso</b>. Se o backup for criptografado, pede a senha.</p>
        <p>A restauração também aceita o arquivo <b>.db</b> das versões antigas do
        DocFlow (e os backups <b>.db</b> gerados por elas) - é assim que os dados de
        uma instalação antiga são trazidos para o banco atual.</p>

        <h2>Trocar de banco de dados</h2>
        <p><b>Banco &gt; Trocar banco de dados...</b> (só admin) - aponta o
        DocFlow pra outro banco PostgreSQL (outro servidor, ou outro banco no mesmo
        servidor) informando servidor, porta, nome do banco, usuário e senha, e
        reinicia o sistema já usando ele. Um banco novo e vazio recebe as tabelas
        automaticamente. A configuração de qual banco usar é guardada por usuário do
        Windows/Linux, não pelo computador inteiro - então, num servidor de Área de
        Trabalho Remota onde cada funcionário loga com sua própria conta, cada um
        pode apontar pro banco do próprio setor sem misturar dados com os outros, ou
        todos apontarem pro mesmo banco se precisarem compartilhar.</p>
        """ + _note(
            "trocar de banco encerra a sessão atual e reabre o sistema do zero. "
            "Cancelar a qualquer momento (a confirmação ou a tela de conexão) não "
            "muda nada."
        ),
    ),
    HelpTopic(
        id="glossario",
        title="Glossário e dúvidas comuns",
        html="""
        <h2>Situação do mês</h2>
        <p>Classificação de uma empresa num mês específico: <b>Não iniciada</b>
        (dentro do prazo, nada marcado), <b>Em andamento</b>, <b>Com pendência</b>
        (algo marcado "Pendente"), <b>Concluída</b>, ou <b>Em atraso</b> (o prazo de
        cobrança desse mês já fechou sem tudo resolvido).</p>

        <h2>Regra de cobrança (início/fim/alerta)</h2>
        <p>Define, pra cada mês de referência (competência), uma janela no mês
        <b>seguinte</b> em que o documento é cobrado. Exemplo: pra competência de
        julho, com início configurado no dia 5 e fim no dia 12, a cobrança fica
        "aberta" de 5 a 12 de <b>agosto</b>. Depois do dia final sem resolução, vira
        "Em atraso". O campo "dias para alerta" marca, dentro da fase de atraso, a
        partir de quantos dias esse item deve ser priorizado pra cobrança. Cada
        empresa pode ter sua própria regra (em <a href="topic:empresas">Empresas</a>)
        ou seguir os prazos gerais (em <a href="topic:configuracoes">
        Configurações</a>).</p>

        <h2>Regra de ocorrência de um tipo de documento</h2>
        <p><b>Mensal</b> - cobrado todo mês. <b>Trimestral</b> - só em março,
        junho, setembro e dezembro (ex: Informe de Rendimentos). <b>Anual em janeiro</b> - só em janeiro; nos demais
        meses o status vira "Não cobrar" sozinho, sem precisar marcar nada.</p>

        <h2>CNPJ alfanumérico</h2>
        <p>Desde 2026 a Receita Federal aceita CNPJs com letras nas 12 primeiras
        posições (mantendo 14 caracteres e os 2 últimos sempre numéricos). O DocFlow
        aceita os dois formatos no cadastro da empresa.</p>

        <h2>Por que um documento não aparece pra cobrar num mês</h2>
        <p>Ou porque a regra de ocorrência do tipo não cobra naquele mês (ex: tipo
        trimestral, mês fora do trimestre), ou porque o status já está "Não cobrar"/
        "Encerrado".</p>
        """,
    ),
]

HELP_TOPICS_BY_ID: dict[str, HelpTopic] = {topic.id: topic for topic in HELP_TOPICS}

DEFAULT_HELP_TOPIC_ID = "inicio"
