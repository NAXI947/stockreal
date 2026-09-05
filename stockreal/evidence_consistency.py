"""Cross-field observations only. Arithmetic agreement does not establish units."""
from datetime import datetime
from decimal import Decimal,InvalidOperation
from zoneinfo import ZoneInfo

def number(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float)):raise ValueError('not numeric')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('not finite')
    return result

def trade_consistency(rows):
    result={'rows':len(rows),'invalid_rows':0,'timestamp_text_agree':0,'known_direction_code':0,
            'ratio_observations':0,'amount_volume_price_ratio_near_100':0,
            'unit_contract_verified':False,'production_eligible':False}
    for row in rows:
        try:
            if not isinstance(row,list) or len(row)!=6:raise ValueError('shape')
            direction,epoch,volume,amount,price,label=row
            if str(direction) in {'1','2','3','4'}:result['known_direction_code']+=1
            timestamp=number(epoch)
            if timestamp!=timestamp.to_integral_value():raise ValueError('fractional epoch')
            decoded=datetime.fromtimestamp(int(timestamp),ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            if decoded==label:result['timestamp_text_agree']+=1
            v,a,p=number(volume),number(amount),number(price)
            if v>0 and p>0:
                ratio=a/(v*p);result['ratio_observations']+=1
                if abs(ratio-100)<=Decimal('0.01'):result['amount_volume_price_ratio_near_100']+=1
        except (ValueError,TypeError,InvalidOperation,OverflowError,OSError):result['invalid_rows']+=1
    return result

def funding_consistency(rows,source):
    positions={41:(7,8,6,19),81:(3,4,5,12)}
    if source not in positions:raise ValueError('unsupported funding source')
    buy,sell,net,width=positions[source]
    result={'rows':len(rows),'invalid_rows':0,'buy_plus_signed_sell_agrees_with_net':0,
            'unit_contract_verified':False,'production_eligible':False}
    for row in rows:
        try:
            if not isinstance(row,list) or len(row)!=width:raise ValueError('shape')
            if abs(number(row[buy])+number(row[sell])-number(row[net]))<=Decimal('0.01'):
                result['buy_plus_signed_sell_agrees_with_net']+=1
        except (ValueError,TypeError,InvalidOperation):result['invalid_rows']+=1
    return result
