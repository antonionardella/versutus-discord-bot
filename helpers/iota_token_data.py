""""
Copyright © Krypton 2022 - https://github.com/kkrypt0nn (https://krypton.ninja)
Description:
This is a template to create your own discord bot in python.

Version: 5.4
"""
import discord
import json
import traceback
import requests
import iota_client_production
import pickle
import datetime
import pandas as pd


from helpers import db_manager
from helpers.logger import logger

with open("config.json") as file:
        config = json.load(file)

def iota_unit_conversion(balance):
    units = ['I', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi']
    conversion_factor = [1, 1000, 1000000, 1000000000, 1000000000000, 1000000000000000]
    for i, unit in enumerate(units):
        if balance < conversion_factor[i]:
            return "{} {}".format(round(balance / conversion_factor[i-1], 2), units[i-1])
    return "{} {}".format(round(balance / conversion_factor[-1], 2), units[-1])

async def get_iota_ledger_state():
    try:
        logger.info("Getting IOTA ledger state")
        # Download the latest ledger state from the IOTA HORNET debug plugin
        debug_plugin_url = 'https://chrysalis.naerd.tech/api/plugins/debug/addresses/ed25519' 
        jwt_token = config["iota_hornet_jwt_token"]

        head = {'Authorization': 'Bearer {}'.format(jwt_token)}
        headers = {'content-type': 'application/json'}

        response = requests.get(url = debug_plugin_url, headers=head)
        chrysalis_reply = response.text 
        data = json.loads(chrysalis_reply)

        await db_manager.add_iota_ledger(data = data, table_name = "iota_hex_addresses")
    
    except Exception as e:
        logger.info(traceback.format_exc())      

async def get_bech32_address_format_iota(ed25519_address):
    bech32_address = iota_client_production.Client().hex_to_bech32(ed25519_address, "iota")
    logger.info(bech32_address)
    logger.info("bech32_address")
    return bech32_address

async def save_iota_rich_list():
    try:
        logger.info("Saving IOTA rich list")
        rows = await db_manager.get_iota_ledger(table_name = "iota_hex_addresses")
        sorted_addresses = sorted(rows, key=lambda x: x[1], reverse=True)
        top_addresses = sorted_addresses[:20]
        # Convert addresses to bech32 format using map function
        top_addresses = list(map(lambda x: (iota_client_production.Client().hex_to_bech32(x[0], "iota"), x[1]), top_addresses))
        await db_manager.add_iota_top_addresses(data = top_addresses, table_name = "iota_top_addresses")
    except Exception as e:
        logger.info(traceback.format_exc())  

async def prepare_iota_richlist_embed():
    logger.info("Preparing IOTA rich list embed")
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    richlist_from_db = await db_manager.get_iota_top_addresses(table_name = "iota_top_addresses")
    complete_richlist = []
    for row in richlist_from_db:
        complete_richlist.append(f"{row[0]} - {row[1]}")
        try:
            # Here we create an embed with the title "IOTA Richlist"          
            embed = discord.Embed(title = "🫰 IOTA Top 5 Richlist", color=0x00FF00)
            for i in range(5):
                if i >= len(complete_richlist):
                    break
                address, balance = complete_richlist[i].split(" - ")
                if int(balance) >= 10**15:
                    balance = f"{float(balance)/10**15:.2f} Pi"
                elif int(balance) >= 10**12:
                    balance = f"{float(balance)/10**12:.2f} Ti"
                elif int(balance) >= 10**9:
                    balance = f"{float(balance)/10**9:.2f} Gi"
                elif int(balance) >= 10**6:
                    balance = f"{float(balance)/10**6:.2f} Mi"
                elif int(balance) >= 10**3:
                    balance = f"{float(balance)/10**3:.2f} ki"
                else:
                    balance = f"{balance} i"
                embed.add_field(name=f"Top Address {i+1}", value=address)
                embed.add_field(name=f"Balance", value=balance)
                embed.add_field(name='', value='', inline=False)
            embed.add_field(name = "Updates: ", value = "Every 24h")
            embed.add_field(name = "Last Update: ", value = current_time)
            with open('embed_iota_richlist.pkl', 'wb') as f:
                pickle.dump(embed, f)
        except Exception as e:
            logger.info(traceback.format_exc())

    logger.info("IOTA richlist embed created")

async def prepare_iota_distribution_embed():
    ledger_state = await db_manager.get_iota_ledger(table_name = "iota_hex_addresses")

    # define the bin edges and labels
    #bin_edges = [1000000, 10000000, 100000000, 1000000000, 10000000000, 100000000000, 1000000000000, 10000000000000, 100000000000000, 1000000000000000]
    bin_edges = [999999, 9999999, 99999999, 999999999, 9999999999, 99999999999, 999999999999, 9999999999999, 99999999999999, 999999999999999]
    labels = ['  1Mi-10Mi', ' 10Mi-100Mi', '100Mi-1Gi', '  1Gi-10Gi', ' 10Gi-100Gi', '100Gi-1Ti', '  1Ti-10Ti', ' 10Ti-100Ti', '100Ti-1Pi']

    # load the data into a pandas DataFrame
    ledger_df = pd.DataFrame(ledger_state, columns=["address", "balance"])

    # add a new column 'range' to the DataFrame that assigns a label to each address based on its balance
    ledger_df['Range'] = pd.cut(ledger_df['balance'], bins=bin_edges, labels=labels)

    # group the DataFrame by the 'range' column and calculate the number of addresses, sum of balances, and percentage of total supply
    summary_table = ledger_df.groupby('Range').agg({'address': 'count', 'balance': 'sum'}).rename(columns={'address': 'Addresses', 'balance': 'Sum balances'})
    
    # Add a new column 'Sum balances (original)' to store the original numeric values
    summary_table['Sum balances (original)'] = summary_table['Sum balances']

    # Convert the values in the 'Sum balances' column to the desired IOTA units using the iota_unit_conversion function
    summary_table['Sum balances'] = summary_table['Sum balances (original)'].apply(iota_unit_conversion)    

    # Calculate the '% Addresses' column using the original numeric values in the 'Addresses' column
    summary_table['% Addresses'] = (summary_table['Addresses'] / summary_table['Addresses'].sum() * 100).round(2)
    summary_table['% Addresses'] = summary_table['% Addresses'].apply(lambda x: "{}%".format(x))

    # Calculate the '% Supply' column using the original numeric values in the 'Sum balances (original)' column
    summary_table['% Supply'] = (summary_table['Sum balances (original)'] / summary_table['Sum balances (original)'].sum() * 100).round(2)
    summary_table['% Supply'] = summary_table['% Supply'].apply(lambda x: "{}%".format(x))

    # Remove the 'Sum balances (original)' column
    summary_table.drop(columns=["Sum balances (original)"], inplace=True)

    # print the summary table
    print(summary_table)

    # Prepare the embed message
    logger.info("Preparing IOTA distribution embed")

    try:
        msg = "**IOTA token distribution**\n\n"
        msg += "```"

        # compute the maximum length of each column
        # col_widths = [len(col) for col in ['Range', 'Addresses', 'Sum balances', '%Addresses', '%Supply']]
        # for row in summary_table.itertuples():
        #     # col_widths = [max(len(str(row[i+1])), width) for i in range(len(col_widths))]
        #     col_widths = [max(len(str(row[i+1])), col_widths[i]) for i in range(len(col_widths))]

        col_widths = [len(col) for col in [' 10Gi-100Gi', 'Addresses', 'Sum balances', '%Addresses', '%Supply']]
        for row in summary_table.itertuples():
            for i in range(len(col_widths)):
                if i+1 < len(row):
                    col_widths[i] = max(len(str(row[i+1])), col_widths[i])

        # build the table header
        header = "|"
        for width in col_widths:
            header += " " + "-"*width + " |"
        msg += header + "\n"

        # build the table header row
        header_row = "|"
        header_row += " " + "Range".ljust(col_widths[0]) + " |"
        header_row += " " + "Addresses".ljust(col_widths[1]) + " |"
        header_row += " " + "Sum balances".ljust(col_widths[2]) + " |"
        header_row += " " + "%Addresses".ljust(col_widths[3]) + " |"
        header_row += " " + "%Supply".ljust(col_widths[4]) + " |"
        msg += header_row + "\n"
        msg += header + "\n"

        # build the table data rows
        for row in summary_table.itertuples():
            data_row = "|"
            #data_row += " " + str(row[0]).rjust(col_widths[0]) + " |"
            data_row += " " + str(row[0]).rjust(col_widths[0]) + " |"
            data_row += " " + str(row[1]).rjust(col_widths[1]) + " |"
            data_row += " " + str(row[2]).rjust(col_widths[2]) + " |"
            data_row += " " + str(row[3]).rjust(col_widths[3]) + " |"
            data_row += " " + str(row[4]).rjust(col_widths[4]) + " |"
            msg += data_row + "\n"
        msg += header + "\n"

        msg += "```"
        msg += "**Data from IOTA Ledger**"


        with open('embed_iota_distribution.pkl', 'wb') as f:
            pickle.dump(msg, f)


    except Exception as e:
        logger.info(traceback.format_exc())


async def main():
    await get_iota_ledger_state()
    await save_iota_rich_list()
    await prepare_iota_richlist_embed()
    await prepare_iota_distribution_embed()


if __name__ == "__main__":
    main()