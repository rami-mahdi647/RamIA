#!/usr/bin/env bash
cat > dataset.csv << 'CSV'
amount,fee,outputs,memo,to_addr,burst_score,timestamp,label
100000,1000,1,hello,abcd1234,0.1,1700000000,0
250000,50,6,FREE MONEY NOW!!!,zzzzzzzzzzzzzzzz,0.9,1700003600,1
50000,800,1,payment,a1b2c3d4e5,0.2,1700007200,0
900000,10,10,airdrop claim,http://spammy.link,1.0,1700010800,1
CSV
echo "dataset.csv created"
