"""Deterministic UI state, formulas and row projections. No generated execution."""
import ast
import math
import re


def validate_formula(expression, inputs, preceding):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 240:
        raise ValueError('Formula must contain 1-240 characters.')
    tokens = re.findall(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[xr][1-9]\d*|[()+\-*/^]|\s+', expression)
    if ''.join(tokens) != expression or len([t for t in tokens if t.strip()]) > 100 or '**' in expression or '//' in expression or re.search(r'(?<![\w.])0[0-9xXbBoO]',expression):
        raise ValueError('Unsupported formula syntax.')
    try:
        tree = ast.parse(expression.strip().replace('^', '**'), mode='eval')
    except (SyntaxError, RecursionError):
        raise ValueError('Invalid arithmetic formula.') from None

    def walk(node, depth=0):
        if depth > 20:
            raise ValueError('Formula nesting exceeds 20.')
        if isinstance(node, ast.Expression): walk(node.body, depth)
        elif isinstance(node, ast.Constant):
            if type(node.value) not in (int, float) or not math.isfinite(node.value) or abs(node.value) > 1e15:
                raise ValueError('Invalid formula number.')
        elif isinstance(node, ast.Name):
            if not re.fullmatch(r'[xr][1-9]\d*', node.id) or int(node.id[1:]) > (inputs if node.id[0] == 'x' else preceding):
                raise ValueError('Unknown or forward formula reference.')
        elif isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow):
            walk(node.left, depth+1); walk(node.right, depth+1)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub): walk(node.operand, depth+1)
        else: raise ValueError('Only arithmetic and declared references are supported.')
    walk(tree)


def evaluate_formula(expression, values, results):
    validate_formula(expression,len(values),len(results))
    tree=ast.parse(expression.strip().replace('^','**'),mode='eval')
    def evaluate(node):
        if isinstance(node,ast.Expression): return evaluate(node.body)
        if isinstance(node,ast.Constant): return float(node.value)
        if isinstance(node,ast.Name):
            value=(values if node.id[0]=='x' else results)[int(node.id[1:])-1]
            if value is None: raise ValueError('Referenced result is unavailable.')
            return float(value)
        if isinstance(node,ast.UnaryOp): return (-1 if isinstance(node.op,ast.USub) else 1)*evaluate(node.operand)
        a,b=evaluate(node.left),evaluate(node.right)
        try:
            if isinstance(node.op,ast.Add): value=a+b
            elif isinstance(node.op,ast.Sub): value=a-b
            elif isinstance(node.op,ast.Mult): value=a*b
            elif isinstance(node.op,ast.Div): value=a/b
            else: value=math.pow(a,b)
        except (OverflowError,ZeroDivisionError,ValueError): raise ValueError('Invalid arithmetic or division by zero.') from None
        if not math.isfinite(value) or abs(value)>1e15: raise ValueError('Result exceeds the calculation range.')
        return value
    return evaluate(tree)


def calculator_results(block, state):
    values=state if isinstance(state,list) else state.get('values') if isinstance(state,dict) else None
    values=values if values is not None else [i['value'] for i in block['inputs']]
    expressions=state.get('expressions') if isinstance(state,dict) else None
    results=[];outputs=[]
    for i,formula in enumerate(block.get('formulas',[])):
        expression=expressions[i] if expressions else formula['expression']
        try:
            value=evaluate_formula(expression,values,results);outputs.append({'label':formula['label'],'expression':expression,'value':value,'unit':formula.get('unit') or block.get('unit','')})
        except ValueError as error:
            value=None;outputs.append({'label':formula['label'],'expression':expression,'value':None,'error':str(error)})
        results.append(value)
    return outputs


def numeric_cell(cell):
    if isinstance(cell,str) and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',cell.strip()): return None
    try: value=float(cell)
    except (TypeError,ValueError): return None
    return value if math.isfinite(value) else None


def validate_table_state(block, value):
    if isinstance(value, str):
        if len(value) > 120: raise ValueError('Table search exceeds 120 characters.')
        return
    if not isinstance(value, dict) or set(value) - {'query','filters','sort','page','pageSize','hidden','selected','widths'}:
        raise ValueError('Unknown table state.')
    columns, rows = len(block.columns), len(block.rows)
    if not isinstance(value.get('query',''), str) or len(value.get('query','')) > 120:
        raise ValueError('Invalid table search.')
    for key in ('page','pageSize'):
        n=value.get(key, 0 if key=='page' else 25)
        if type(n) is not int or (key=='page' and not 0<=n<=1000) or (key=='pageSize' and n not in (10,25,50,100)):
            raise ValueError('Invalid pagination.')
    for key, limit in (('hidden',columns), ('selected',rows)):
        indexes=value.get(key,[])
        if not isinstance(indexes,list) or len(set(map(str,indexes)))!=len(indexes) or any(type(i) is not int or not 0<=i<limit for i in indexes):
            raise ValueError('Invalid table indexes.')
    if len(value.get('hidden',[]))>=columns: raise ValueError('Keep at least one column visible.')
    sort=value.get('sort')
    if sort is not None and (not isinstance(sort,dict) or set(sort)!= {'column','direction'} or type(sort['column']) is not int or not 0<=sort['column']<columns or sort['direction'] not in ('asc','desc')):
        raise ValueError('Invalid table sorting.')
    for key in ('filters','widths'):
        entries=value.get(key,{})
        if not isinstance(entries,dict): raise ValueError('Invalid column state.')
        for col, item in entries.items():
            if not isinstance(col,str) or not col.isascii() or not col.isdigit() or str(int(col))!=col or not 0<=int(col)<columns:
                raise ValueError('Unknown column.')
            if key=='filters' and (not isinstance(item,str) or len(item)>120): raise ValueError('Invalid column filter.')
            if key=='widths' and (type(item) not in (float,int) or not 64<=item<=600): raise ValueError('Invalid column width.')


def project_table(block, value, scope):
    """Return actual saved rows; selecting rows never widens source scope."""
    value={'query':value} if isinstance(value,str) else value or {}
    rows=[(i,r) for i,r in enumerate(block['rows']) if any(value.get('query','').lower() in str(c).lower() for c in r)
          and all(q.lower() in str(r[int(col)]).lower() for col,q in value.get('filters',{}).items())]
    if value.get('sort'):
        col=value['sort']['column']
        def key(item):
            cell=item[1][col]
            n=numeric_cell(cell)
            return (0,n) if n is not None else (1,tuple((0,int(t)) if t.isdigit() else (1,t) for t in re.split(r'(\d+)',str(cell).lower()) if t))
        rows.sort(key=key,reverse=value['sort']['direction']=='desc')
    if scope=='selected': rows=[r for r in rows if r[0] in value.get('selected',[])]
    elif scope=='visible':
        size=value.get('pageSize',25);page=min(value.get('page',0),max(0,math.ceil(len(rows)/size)-1))
        rows=rows[page*size:(page+1)*size]
    totals=[]
    for col,name in enumerate(block['columns']):
        values=[numeric_cell(r[col]) for _,r in rows]
        if values and all(v is not None for v in values):
            total=sum(values)
            totals.append({'column':name,'count':len(values),'sum':total,'average':total/len(values),'min':min(values),'max':max(values)})
    return {'columns':block['columns'],'rows':[r for _,r in rows],'row_ids':[i for i,_ in rows],'verified_aggregates':totals,
            'scope':scope,'dataset_rows':len(block['rows']),'query':value.get('query',''),'filters':value.get('filters',{})}
