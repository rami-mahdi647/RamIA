require('@nomiclabs/hardhat-ethers');

module.exports = {
  solidity: '0.8.20',
  networks: {
    hardhat: {},
    mainnet: {
      url: process.env.ETH_RPC,
      accounts: [process.env.PRIVATE_KEY]
    },
    polygon: {
      url: process.env.POLYGON_RPC,
      accounts: [process.env.PRIVATE_KEY]
    },
    bnb: {
      url: process.env.BNB_RPC,
      accounts: [process.env.PRIVATE_KEY]
    }
  }
};
