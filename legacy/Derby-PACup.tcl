proc U21 {year} {
  if {1991 < $year && $year < 1995} { 
    [return 1] 
  } else {
    [return 0]
  }
}

proc U18 {year} {
  if {1994 < $year && $year < 1997} { 
    [return 1] 
  } else {
    [return 0]
  }
}

proc U16 {year} {
  if {1996 < $year && $year < 1999} { 
    [return 1] 
  } else {
    [return 0]
  }
}


proc U21U18 {year} {
  if {1991 < $year && $year < 1997} { 
    [return 1] 
  } else {
    [return 0]
  }
}

proc U21U18U16 {year} {
  if {1991 < $year && $year < 1999} { 
    [return 1] 
  } else {
    [return 0]
  }
}

proc class {year} {
  if {$year < 1992} {
    return "Master"
  } elseif {$year < 1995} {
    return "U21"
  } elseif {$year < 1997} {
    return "U18"
  } elseif {$year < 1999} {
    return "U16"
  } elseif {$year < 2001} {
    return "U14"
  } elseif {$year < 2003} {
    return "U12"
  } elseif {$year < 2005} {
    return "U10"
  } else {
    return "Too Young"
  }
}
   
proc WC {plc} {
  if {$plc > 30} {return 0}
  return [lindex {-1 100 80 60 50 45 40 36 32 29 26 24 22 20 18 16 15 14 13 12 11 10 9 8 7 6 5 4 3 2 1} $plc]
}

puts "Processing Registration Data File.."
set fp [open Registration.csv]
set file_data [read -nonewline $fp]
close $fp
set header {ID FIS Last First Club State Year Sex Type}
set splitCont [split $file_data "\n"]
set count 0
foreach ele $splitCont {
  foreach $header [split $ele ","] {
     set Reg($ID,Last) $Last
     set Reg($ID,First) $First
     set Reg($ID,State) $State
     set Reg($ID,Year) $Year
     set Reg($ID,Sex) $Sex
     set Reg($ID,Club) $Club
     set Reg($ID,FIS) $FIS     
  }
}


set CLASSES {U21U18U16 U21 U18 U16 U21U18}
set CLUBS {BKST BMRA BMSC DCWST EMSC HVRC JFRT LMRT PASEF SHAW SNO SMRT SRRC SSRT TMART WPRC WTSEF}
set RACES {Wisp-SL1 Wisp-SL2 Blue-GS3 Blue-GS4 Blue-SL5 Elk-GS6 Elk-GS7 Elk-SL8}
set SEXS {Men Women}
foreach Sex $SEXS {
  #clear racer info
  if {[info exist RACERS]} {
     foreach one $RACERS {unset $one}
     unset RACERS
  }

  ;#set RACE [lindex $RACES 0]
  foreach RACE $RACES {
    puts "Processing $Sex Race Data File ... $RACE-$Sex.cvs"
    set fp [open $RACE-$Sex.csv]
    set file_data [read -nonewline $fp]
    close $fp
    set splitCont [split $file_data "\n"]
    set count 0
    set header {id last first club year r1 r2 total}
    foreach ele $splitCont {
;#      puts "[incr count] $ele"
      foreach $header [split $ele ","] {
        if {[lsearch $CLUBS $club] != -1} {
		       if {[array exist $id] == 0} {
		          foreach h [lrange $header 1 end-3] {set [set id]($h) [set $h]}
		          lappend RACERS $id
		  ;#        puts "in here"
		          if {[info exist Reg($id,Club)]} {
		             set [set id](club) $Reg($id,Club)
		             set [set id](sex) $Reg($id,Sex) 		          
		             set [set id](state) $Reg($id,State) 		          
		             set [set id](fis) $Reg($id,FIS)
		             set [set id](class) [class [set [set id](year)]]
		          } else {
		             puts "need to add to reg file> $ele "
		          }
		       }
		         
		       if {$total != ""} {
		          set [set id]($RACE,time) $total
		       } elseif {[string is double $r1]} {
		          set [set id]($RACE,time) $r2
		       } else {
		          set [set id]($RACE,time) $r1
		       }
		    } else {
		       puts "$id. $last, $first, $club - excluded"
		    }                     
        ;#puts "$count. $id .. $last  .. $first .. $club $year $total"
      }
    }
  }

  ;# determine overall place U21U18U16  
  foreach cls $CLASSES {
    foreach RACE $RACES {
      puts "Processing $Sex Race $cls ... $RACE"
      if {[info exist [set RACE](times)]} {
        unset [set RACE](times)
        unset [set RACE](id)
      }
      foreach a $RACERS {
        if {[info exist [set a]($RACE,time)]} {
          if {[string is double [set [set a]($RACE,time)]]} {
            if {[[set cls] [set [set a](year)]]} {
             ;# puts "in here"
              lappend [set RACE](times) [set [set a]($RACE,time)]
              lappend [set RACE](id) [set a]
            }
          }     
        }
      }
      if {[info exist [set RACE](times)]} {
        set [set RACE](times) [lsort -real -increasing [set [set RACE](times)]]
        foreach id [set [set RACE](id)] {
          set [set id]($RACE,$cls) [expr [lsearch [set [set RACE](times)] [set [set id]($RACE,time)]]+1]
        }
      }
    }
  }
  
  
  ;# print out the results
  foreach cls $CLASSES {
   puts "Class $cls results"
   set fileId [open Results-$Sex-$cls.csv "w"]
   set header "RANK,USSA,FIS,STATE,LAST,FIRST,CLUB,YEAR,CLASS"
   foreach r $RACES {set header "$header,[split $r -] Pts"}
   puts $fileId "$header,POINTS"
   foreach a $RACERS {
     if {[[set cls] [set [set a](year)]]} {
       set summary {}
       set points 0
       foreach RACE $RACES {
          if {[info exist [set a]($RACE,$cls)]} {
              set summary "$summary,[set tmp [WC [set [set a]($RACE,$cls)]]]"
              incr points $tmp
          } elseif {[info exist [set a]($RACE,time)]} {
              set summary "$summary,[set [set a]($RACE,time)]"            
          } else {
              set summary "$summary, "
          }
       }
       set fis " "
       if {[set [set a](fis)]!="NULL"} {set fis Y}
       puts $fileId " ,$a,$fis,[set [set a](state)],[set [set a](last)],[set [set a](first)],[set [set a](club)],[set [set a](year)],[set [set a](class)]$summary,$points,"
     }
   }
   close $fileId
  }
}