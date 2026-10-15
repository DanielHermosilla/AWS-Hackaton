import csv,json,pathlib,urllib.request,time,datetime,hashlib
# Prepares the public design example only. This is not a generic scenario loader.
import argparse
parser=argparse.ArgumentParser(description='Prepare the local public design fixture; sends its stop coordinates to the public OSRM service.')
parser.add_argument('csv_path',type=pathlib.Path)
parser.add_argument('--permitir-osrm-publico',action='store_true',help='Consentimiento explícito: envía las coordenadas de las paradas a router.project-osrm.org (servicio de terceros). No usar con direcciones reales de clientes.')
parser.add_argument('--osrm-url',default='https://router.project-osrm.org',help='Servidor OSRM (usar uno propio para datos reales).')
args=parser.parse_args()
root=pathlib.Path(__file__).resolve().parent
rows=list(csv.DictReader(open(args.csv_path,encoding='utf-8-sig')))
if len(rows)>2000:raise SystemExit('CSV demasiado grande para la demostración')
nodes=[dict(id=r['node_id'],type=r['node_type'] if r['node_type'] in ['base','visit'] else 'charger',lat=float(r['latitude']),lng=float(r['longitude']),label='Centro de distribución' if r['node_type']=='base' else ('Local '+r['node_id'][1:] if r['node_type']=='visit' else 'Cargador '+r['node_id'][1:]),connectors=r['connector_types'],maxPowerKw=float(r['max_power_kw']) if r['max_power_kw'] else None) for r in rows]
by={n['id']:n for n in nodes}
seqs=[['BASE','V12','V3','V6','V19','V7','V15','V14','V1','C3','V16','V13','BASE'],['BASE','V5','V9','V2','C9','V10','V20','V4','V17','V8','V18','V11','BASE']]
levels=[[60,57,50,46,40,35,32,28,25,22,47,41,37.5],[60,57,51,48,46,63,59,55,52,48,45,43,41.25]]
routes=[]
for i,seq in enumerate(seqs):
 cache=root/('osrm-auto-'+str(i+1)+'.local.json')
 coords=';'.join(str(by[n]['lng'])+','+str(by[n]['lat']) for n in seq)
 url=args.osrm_url.rstrip('/')+'/route/v1/driving/'+coords+'?overview=full&geometries=geojson&steps=false'
 if cache.exists():data=json.loads(cache.read_text(encoding='utf-8'))
 else:
  if args.osrm_url.startswith('https://router.project-osrm.org') and not args.permitir_osrm_publico:raise SystemExit('Falta --permitir-osrm-publico: este paso envía coordenadas al OSRM público.')
  if not args.osrm_url.startswith('https://'):raise SystemExit('--osrm-url debe usar https://')
  req=urllib.request.Request(url,headers={'User-Agent':'ZMD-Mobility-Design-Exploration/1.0'})
  data=json.loads(urllib.request.urlopen(req,timeout=45).read(20_000_000).decode('utf-8'));cache.write_text(json.dumps(data),encoding='utf-8');time.sleep(1.1)
 if data.get('code')!='Ok':raise RuntimeError(data)
 q=4.5 if i==0 else 3.2
 stops=[]
 for j,nid in enumerate(seq):
  charge=q if by[nid]['type']=='charger' else 0
  stops.append(dict(nodeId=nid,arrivalSoc=levels[i][j],departureSoc=levels[i][j]+charge/16*100,chargeKwh=charge))
  if by[nid]['type']!='base':by[nid]['vehicleId']='auto-'+str(i+1)
 routes.append(dict(vehicleId='auto-'+str(i+1),stopIds=seq,energyKwh=[8.1,6.2][i],chargeKwh=q,finalSoc=levels[i][-1],geometry=data['routes'][0]['geometry'],stops=stops,distanceKm=round(data['routes'][0]['distance']/1000,1)))
fixture=dict(SCENARIO=dict(id='design-round2',name='Ann Arbor',fileName='competition_routing_nodes.csv',demonstration=True,deliveryCount=20,chargerCount=60,computeSeconds=None,fixtureBatteryKwh=16,provenance='Coordenadas del escenario público. Orden de visitas y energía inventados para diseño; calles OSRM. Sin optimización ni validación energética.'),VEHICLES=[dict(id='auto-'+str(i+1),name='Auto '+str(i+1),model='Nissan Leaf 2013',initialSoc=60,color=['#1664ec','#8152d9'][i]) for i in range(2)],NODES=nodes,ROUTES=routes)
(root/'fixture.local.json').write_text(json.dumps(fixture,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
(root/'provenance.local.json').write_text(json.dumps(dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),geometrySource='OSRM public route service',rawFilesIgnored=True,notes=fixture['SCENARIO']['provenance'],battery='16 kWh is a design fixture only; fixed SOC steps are authored, not predictions.'),indent=2),encoding='utf-8')
print(json.dumps([dict(id=r['vehicleId'],km=r['distanceKm'],points=len(r['geometry']['coordinates']),stops=len(r['stops'])) for r in routes]))
